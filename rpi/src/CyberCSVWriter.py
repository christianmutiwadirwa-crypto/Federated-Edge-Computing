"""
=============================================================================
 CyberCSVWriter.py
 Thread-safe writer for windowed cyber feature vectors to CSV.
=============================================================================
 Consumes feature dicts from the shared cyber_queue (produced by WindowManager)
 and appends one row per completed observation window to cyber_data.csv.

 Each row represents exactly one 2-second observation window, not one packet.

 CSV column order mirrors the HEADERS list below and the output of
 CyberFeatureExtractor.extract().
=============================================================================
"""

import csv
import queue
import threading
import time
from pathlib import Path


class CyberCSVWriter:
    """
    Thread-safe CSV writer for windowed cyber feature vectors.

    Runs a dedicated background thread (CyberWriterThread) that continuously
    drains the cyber_queue and appends rows to the CSV file.

    The file is created (with headers) on startup if it does not already exist.
    Rows are buffered in the OS write buffer and flushed every csv_flush_interval_sec
    seconds to balance I/O efficiency against data durability.
    """

    # Exact CSV column order — must match CyberFeatureExtractor.extract() output.
    HEADERS = [
        # Window Information
        "window_id",
        "window_start_time",
        "window_end_time",

        # Identity Features
        "node_id",
        "src_ip",
        "dst_ip",
        "src_port",
        "dst_port",

        # Traffic Volume Features
        "total_packets",
        "total_bytes",
        "packet_rate",
        "data_rate",

        # Packet Size Statistics
        "mean_packet_size",
        "std_packet_size",
        "min_packet_size",
        "max_packet_size",

        # Timing Features
        "mean_interarrival_time",
        "std_interarrival_time",
        "min_interarrival_time",
        "max_interarrival_time",
        "connection_duration",

        # Reliability Features
        "packet_loss_rate",
        "duplicate_packet_count",
        "out_of_order_packet_count",
        "sequence_number_gap",
        "reconnection_count",

        # Integrity Features
        "crc_failure_count",
        "crc_failure_rate",
        "invalid_packet_count",
        "invalid_packet_rate",

        # Behaviour Features
        "burst_intensity",
        "mean_sequence_increment",
        "std_sequence_increment",

        # Label
        "AttackLabel",
    ]

    def __init__(self, config_manager, data_queue: queue.Queue):
        """
        Args:
            config_manager : Provides file-path config and flush interval.
            data_queue     : Queue of feature dicts produced by WindowManager.
        """
        self.data_queue     = data_queue
        self.running        = True
        self.flush_interval = config_manager.get("csv_flush_interval_sec", 5)

        # Resolve output path from config
        base_dir  = Path(config_manager.get("directories", {}).get("base",  "EdgeNode"))
        cyber_dir = base_dir / config_manager.get("directories", {}).get("cyber", "cyber")
        self.file_path = cyber_dir / "cyber_data.csv"

        # Create file and write headers if the file is new or empty
        self._ensure_header()

        # Start background writer thread
        self.thread = threading.Thread(
            target=self._writer_worker,
            name="CyberWriterThread",
            daemon=True,
        )
        self.thread.start()

    # ------------------------------------------------------------------
    # Header initialisation
    # ------------------------------------------------------------------

    def _ensure_header(self) -> None:
        """Write the CSV header row if the file does not exist or is empty."""
        write_header = (
            not self.file_path.exists()
            or self.file_path.stat().st_size == 0
        )
        if write_header:
            with open(self.file_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(self.HEADERS)

    # ------------------------------------------------------------------
    # Background writer
    # ------------------------------------------------------------------

    def _writer_worker(self) -> None:
        """
        Background thread: drain the cyber_queue and append rows to the CSV.

        Rows are written in the order they arrive.  The file handle is kept
        open for the lifetime of the thread to avoid repeated open/close overhead.
        The OS buffer is flushed every flush_interval seconds.
        """
        last_flush = time.time()

        with open(self.file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            while self.running or not self.data_queue.empty():
                try:
                    data = self.data_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                try:
                    # Build the row in HEADERS column order.
                    # Numeric columns default to 0; AttackLabel defaults to "Normal".
                    row = [
                        data.get(col, "Normal" if col == "AttackLabel" else 0)
                        for col in self.HEADERS
                    ]
                    writer.writerow(row)
                    self.data_queue.task_done()

                    # Periodic flush
                    now = time.time()
                    if now - last_flush >= self.flush_interval:
                        f.flush()
                        last_flush = now

                except Exception as e:
                    print(f"[CyberCSVWriter] Row write error: {e}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """
        Signal the writer thread to stop and wait for it to drain the queue.
        Call this AFTER WindowManager.stop() to ensure all windows are enqueued.
        """
        self.running = False
        self.thread.join()
