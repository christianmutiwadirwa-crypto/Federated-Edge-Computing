"""
=============================================================================
 SlidingWindow.py
 Time-based packet accumulator for a single node observation window.
=============================================================================
 Exports:
   PacketEntry  — Immutable record of one received packet (valid or invalid)
                  enriched with per-packet computed metrics.
   SlidingWindow — Time-based buffer that holds PacketEntry objects for the
                   duration of one observation window. Owned by WindowManager.

 Design notes:
   - The window uses a TUMBLING (non-overlapping) model: packets accumulate
     from window_start until window_duration elapses, then are flushed atomically.
   - Thread-safety is guaranteed by an internal RLock on all public methods.
   - The window_start timestamp is set on the FIRST packet arrival, not at
     object creation time, so no artificial zero-padding occurs at startup.
=============================================================================
"""

import threading
import statistics
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# PacketEntry
# ---------------------------------------------------------------------------

class PacketEntry:
    """
    Immutable record of one received TCP packet from an ESP32 node.

    Created by DataManager._validation_worker and consumed by CyberFeatureExtractor.
    Carries both raw values and per-packet computed metrics so the extractor
    remains stateless.

    Attributes:
        arrival_time         (float) : Server-side Unix timestamp of packet receipt.
        node_id              (int)   : ESP32 node identifier; -1 if unidentifiable.
        src_ip               (str)   : Source IP address of the ESP32.
        dst_ip               (str)   : Destination IP (server) address.
        src_port             (int)   : Ephemeral source port of the ESP32.
        dst_port             (int)   : Server listening port (9000).
        size                 (int)   : Raw byte count of the received packet.
        seq                  (int)   : Sequence number from packet header; -1 if invalid.
        inter_arrival_time   (float) : Seconds since previous valid packet; 0.0 for first.
        seq_gap              (int)   : Missing sequence numbers before this packet; 0 if none.
        is_duplicate         (bool)  : True if seq matches the previous latest sequence.
        is_out_of_order      (bool)  : True if seq < previous latest sequence.
        is_valid             (bool)  : True if packet passed CRC and format checks.
        crc_pass             (bool)  : True if CRC-16 verified successfully.
        connection_start_time(float) : Unix timestamp of the first ever packet from
                                       this node in the current session. Used to
                                       compute connection_duration at flush time.
                                       None for invalid packets with unknown node.
    """

    __slots__ = (
        "arrival_time", "node_id", "src_ip", "dst_ip", "src_port", "dst_port",
        "size", "seq", "inter_arrival_time", "seq_gap",
        "is_duplicate", "is_out_of_order", "is_valid", "crc_pass",
        "connection_start_time",
    )

    def __init__(
        self,
        arrival_time: float,
        node_id: int,
        src_ip: str,
        dst_ip: str,
        src_port: int,
        dst_port: int,
        size: int,
        seq: int,
        inter_arrival_time: float,
        seq_gap: int,
        is_duplicate: bool,
        is_out_of_order: bool,
        is_valid: bool,
        crc_pass: bool,
        connection_start_time: Optional[float],
    ):
        self.arrival_time          = arrival_time
        self.node_id               = node_id
        self.src_ip                = src_ip
        self.dst_ip                = dst_ip
        self.src_port              = src_port
        self.dst_port              = dst_port
        self.size                  = size
        self.seq                   = seq
        self.inter_arrival_time    = inter_arrival_time
        self.seq_gap               = seq_gap
        self.is_duplicate          = is_duplicate
        self.is_out_of_order       = is_out_of_order
        self.is_valid              = is_valid
        self.crc_pass              = crc_pass
        self.connection_start_time = connection_start_time

    def __repr__(self) -> str:
        return (
            f"PacketEntry(node={self.node_id}, seq={self.seq}, "
            f"valid={self.is_valid}, t={self.arrival_time:.3f})"
        )


# ---------------------------------------------------------------------------
# SlidingWindow
# ---------------------------------------------------------------------------

class SlidingWindow:
    """
    Time-based packet buffer for a single node's observation window.

    Accumulates PacketEntry objects from the moment the first packet arrives
    until window_duration_sec has elapsed since that first packet. The
    WindowManager polls is_expired() and calls flush() to collect the batch
    and reset for the next window.

    Thread-safety:
        All public methods are protected by an internal RLock. This allows
        concurrent access from the DataManager validation thread (add_packet)
        and the WindowManager timer thread (is_expired / flush).
    """

    def __init__(self, window_duration_sec: float):
        """
        Args:
            window_duration_sec: Duration of each observation window in seconds.
                                 Should match the ESP32's feature extraction interval.
        """
        self._window_duration: float = window_duration_sec
        self._lock = threading.RLock()
        self._packets: List[PacketEntry] = []
        self._window_start: Optional[float] = None   # Set on first packet arrival

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def add_packet(self, entry: PacketEntry) -> None:
        """
        Append a PacketEntry to the active window buffer.

        If this is the first packet of a new window, records the window
        start time from the packet's arrival_time.

        Args:
            entry: The PacketEntry to buffer.
        """
        with self._lock:
            if self._window_start is None:
                self._window_start = entry.arrival_time
            self._packets.append(entry)

    def is_expired(self, now: float) -> bool:
        """
        Check whether the current window has elapsed its full duration.

        Returns True only when:
          - At least one packet has been buffered (window_start is set), AND
          - now - window_start >= window_duration_sec

        Empty windows (no packets received) never expire; they are skipped.

        Args:
            now: Current Unix timestamp (time.time()).

        Returns:
            True if the window is ready to be flushed.
        """
        with self._lock:
            if self._window_start is None:
                return False
            return (now - self._window_start) >= self._window_duration

    def flush(self, flush_time: float) -> Tuple[List[PacketEntry], float, float]:
        """
        Atomically retrieve all buffered packets and reset for the next window.

        This is the only method that removes packets from the buffer. After
        this call, the window is empty and ready for the next observation period.

        Args:
            flush_time: The Unix timestamp at which the flush was triggered.
                        Used as window_end_time in the feature vector.

        Returns:
            Tuple of (packets, window_start, window_end):
              - packets      : List of buffered PacketEntry objects (never None).
              - window_start : Unix timestamp of the first packet in the window.
              - window_end   : The flush_time argument (window close timestamp).
        """
        with self._lock:
            packets      = self._packets
            window_start = self._window_start
            # Reset state for the next window
            self._packets      = []
            self._window_start = None
            return packets, window_start, flush_time

    def is_active(self) -> bool:
        """
        Returns True if this window contains at least one buffered packet.
        Used by WindowManager.flush_all() during graceful shutdown.
        """
        with self._lock:
            return self._window_start is not None

    @property
    def packet_count(self) -> int:
        """Current number of buffered packets (informational)."""
        with self._lock:
            return len(self._packets)
