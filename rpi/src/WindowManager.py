"""
=============================================================================
 WindowManager.py
 Per-node tumbling observation window manager.
=============================================================================
 Architecture:

   PacketReceiver
       ↓
   DataManager._validation_worker
       ├─ build PacketEntry
       └─ WindowManager.add_packet(entry)
                ↓
           NodeWindow (SlidingWindow, one per node_id)
                ↓ (timer thread every 50ms)
           _flush_expired_windows()
                ↓
           CyberFeatureExtractor.extract(window_batch)
                ↓
           cyber_queue → CyberCSVWriter

 Design principles:
   - One SlidingWindow per node_id.  Each node's window expires independently.
   - Timer thread polls at 50ms resolution — much finer than the 2s window,
     so flush timing is accurate to within one poll interval.
   - The lock is held only for buffer manipulation (fast path).
     Feature extraction and queue writes happen OUTSIDE the lock (slow path).
   - AttackLabel is read from a plain-text file at flush time for zero-coupling
     between the data-collection process and the attack framework process.
   - Graceful shutdown calls flush_all() to emit any partial window before exit.
=============================================================================
"""

import time
import threading
import queue
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from SlidingWindow import SlidingWindow, PacketEntry
from CyberFeatureExtractor import CyberFeatureExtractor
from ConnectionStateManager import ConnectionStateManager
from Logger import Logger


class WindowManager:
    """
    Manages per-node tumbling observation windows.

    One SlidingWindow is maintained per connected node_id.  Every
    window_duration_sec, all buffered packets are flushed: the
    CyberFeatureExtractor computes the full feature vector and the result
    is pushed onto the shared cyber_queue for CyberCSVWriter to persist.
    """

    # Timer thread poll interval (seconds).
    # Must be << window_duration_sec for accurate flush timing.
    _POLL_INTERVAL_SEC: float = 0.05   # 50 ms

    def __init__(
        self,
        config_manager,
        connection_manager: ConnectionStateManager,
        cyber_queue: queue.Queue,
        inference_queue: queue.Queue,
        latest_physical: dict,
        logger: Logger,
    ):
        """
        Args:
            config_manager     : Provides window_duration_sec and directory config.
            connection_manager : Shared ConnectionStateManager for drain_reconnections().
            cyber_queue        : Queue consumed by CyberCSVWriter.
            logger             : Shared Logger instance.
        """
        self._window_duration: float   = config_manager.get("window_duration_sec", 2)
        self._connection_manager       = connection_manager
        self._cyber_queue              = cyber_queue
        self._inference_queue          = inference_queue
        self._latest_physical          = latest_physical
        self._logger                   = logger

        # One CyberFeatureExtractor instance (stateless — safe to share)
        self._extractor = CyberFeatureExtractor(config_manager)

        # Base state directory for potential future IPC
        base_dir = Path(config_manager.get("directories", {}).get("base", "EdgeNode"))
        state_dir = base_dir / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        # Per-node windows  {node_id → SlidingWindow}
        self._windows: Dict[int, SlidingWindow] = {}
        self._windows_lock = threading.Lock()

        # Global, monotonically-increasing window ID
        self._window_id: int      = 0
        self._window_id_lock      = threading.Lock()

        # Timer thread
        self._running: bool = True
        self._timer_thread = threading.Thread(
            target=self._flush_loop,
            name="WindowManagerTimerThread",
            daemon=True,
        )
        self._timer_thread.start()

    # ------------------------------------------------------------------
    # Public interface (called from DataManager validation thread)
    # ------------------------------------------------------------------

    def add_packet(self, entry: PacketEntry) -> None:
        """
        Add a PacketEntry to the appropriate per-node window buffer.

        If no window exists for the entry's node_id, one is created.
        Packets with node_id == -1 (unidentifiable) are silently dropped
        because they cannot be associated with any known node window.

        Args:
            entry: Fully populated PacketEntry (valid or invalid packet).
        """
        if entry.node_id < 0:
            # Cannot associate with a node window; skip.
            return

        with self._windows_lock:
            if entry.node_id not in self._windows:
                self._windows[entry.node_id] = SlidingWindow(self._window_duration)
            self._windows[entry.node_id].add_packet(entry)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def flush_all(self) -> None:
        """
        Force-flush all active windows immediately.

        Called during graceful shutdown to ensure no buffered packets are lost.
        Partial windows (fewer than window_duration_sec of data) are emitted as-is.
        """
        now = time.time()
        # Snapshot the window dict to avoid holding the lock during flush
        with self._windows_lock:
            snapshot = {
                nid: win for nid, win in self._windows.items() if win.is_active()
            }
        for node_id, window in snapshot.items():
            packets, window_start, window_end = window.flush(now)
            if packets:
                self._emit_window(node_id, packets, window_start, window_end)

    def stop(self) -> None:
        """
        Stop the timer thread and perform a final flush of all windows.

        Must be called before CyberCSVWriter.stop() so that any buffered
        partial windows are written to the cyber_queue before the writer exits.
        """
        self._running = False
        self._timer_thread.join(timeout=2.0)
        self.flush_all()

    # ------------------------------------------------------------------
    # Timer thread
    # ------------------------------------------------------------------

    def _flush_loop(self) -> None:
        """
        Background thread: checks every _POLL_INTERVAL_SEC for expired windows.
        """
        while self._running:
            time.sleep(self._POLL_INTERVAL_SEC)
            self._flush_expired(time.time())

    def _flush_expired(self, now: float) -> None:
        """
        Identify and flush all expired windows without holding the lock
        during the (potentially slow) feature extraction step.
        """
        # --- Critical section: collect expired batches under lock ---
        to_emit: List[Tuple[int, List[PacketEntry], float, float]] = []

        with self._windows_lock:
            for node_id, window in self._windows.items():
                if window.is_expired(now):
                    packets, window_start, window_end = window.flush(now)
                    if packets:                        # Skip truly empty windows
                        to_emit.append((node_id, packets, window_start, window_end))

        # --- Slow path: feature extraction + queue write outside lock ---
        for node_id, packets, window_start, window_end in to_emit:
            self._emit_window(node_id, packets, window_start, window_end)

    # ------------------------------------------------------------------
    # Window emission
    # ------------------------------------------------------------------

    def _emit_window(
        self,
        node_id: int,
        packets: List[PacketEntry],
        window_start: float,
        window_end: float,
    ) -> None:
        """
        Extract features from a completed window and push to the cyber queue.

        Args:
            node_id       : ESP32 node identifier.
            packets       : All PacketEntry objects buffered in this window.
            window_start  : Unix timestamp of the first packet in the window.
            window_end    : Unix timestamp when the window was flushed.
        """
        # Assign a unique, monotonically-increasing window ID
        with self._window_id_lock:
            window_id = self._window_id
            self._window_id += 1

        # Drain the per-window reconnection count from session state
        node_state = self._connection_manager.get_or_create(node_id)
        reconnection_count = node_state.drain_reconnections()

        # Compute the full feature vector
        try:
            features = self._extractor.extract(
                window_id=window_id,
                window_start=window_start,
                window_end=window_end,
                packets=packets,
                reconnection_count=reconnection_count,
            )
        except Exception as e:
            self._logger.log(
                f"CyberFeatureExtractor error (window_id={window_id}, node={node_id}): {e}",
                severity="ERROR",
            )
            return

        # Push to the CSV writer queue
        try:
            self._cyber_queue.put_nowait(features)
        except queue.Full:
            self._logger.log(
                f"Cyber queue full. Window {window_id} (node={node_id}) dropped.",
                severity="ERROR",
            )

        # Build window dict for InferenceEngine and push to inference_queue
        inference_window = {
            "cyber": features,
            "physical": self._latest_physical.get(node_id, None),
            "window_timestamp": features.get("window_start_time"),
            "node_id": node_id,
        }
        try:
            self._inference_queue.put_nowait(inference_window)
        except queue.Full:
            pass # Inference queue is non-blocking drop-if-full to prevent memory leaks


