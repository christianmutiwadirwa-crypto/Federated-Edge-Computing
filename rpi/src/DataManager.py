"""
=============================================================================
 DataManager.py
 Central packet processing orchestrator for the Raspberry Pi Edge Node.
=============================================================================
 Thread model:
   Thread 1 : PacketReceiver(s)  — one per ESP32 connection (spawned by TCPServer)
   Thread 2 : _validation_worker — packet parsing, metric computation, dispatch
   Thread 3 : PhysicalWriterThread — inside PhysicalCSVWriter
   Thread 4 : WindowManagerTimerThread — inside WindowManager (2s flush timer)
   Thread 5 : CyberWriterThread — inside CyberCSVWriter

 Data flow:
   PacketReceiver
       ↓ process_raw_packet()  [Thread 1 → validation_queue]
   _validation_worker          [Thread 2]
       ├─ parse + validate (PacketParser)
       ├─ if VALID:
       │    ├─ compute per-packet metrics (ConnectionStateManager)
       │    ├─ build PacketEntry
       │    ├─ forward to physical_queue → PhysicalCSVWriter [Thread 3]
       │    └─ forward to WindowManager.add_packet()
       └─ if INVALID (node_id known):
            └─ build minimal PacketEntry (is_valid=False)
               forward to WindowManager.add_packet()
                   ↓ (every 2 s, Thread 4)
               WindowManager → CyberFeatureExtractor → cyber_queue
                   ↓ [Thread 5]
               CyberCSVWriter
=============================================================================
"""

import queue
import threading

from PacketParser import PacketParser
from ConnectionStateManager import ConnectionStateManager
from WindowManager import WindowManager
from PhysicalCSVWriter import PhysicalCSVWriter
from CyberCSVWriter import CyberCSVWriter
from SlidingWindow import PacketEntry
from Logger import Logger


class DataManager:
    """Orchestrates packet validation, routing, and feature extraction."""

    def __init__(self, config_manager, logger: Logger):
        """
        Instantiate all sub-systems and start background threads.

        Args:
            config_manager : Provides queue sizes, directory paths, window config.
            logger         : Shared Logger instance for event logging.
        """
        self.logger         = logger
        self.config_manager = config_manager

        # --- Queues ---
        q = config_manager.get("queue_sizes", {})
        self.validation_queue = queue.Queue(maxsize=q.get("validation_queue",    1000))
        self.physical_queue   = queue.Queue(maxsize=q.get("physical_writer_queue", 1000))
        self.cyber_queue      = queue.Queue(maxsize=q.get("cyber_writer_queue",  1000))

        # --- Core processing components ---
        self.parser             = PacketParser()
        self.connection_manager = ConnectionStateManager()

        # --- Writers ---
        self.physical_writer = PhysicalCSVWriter(config_manager, self.physical_queue)
        self.cyber_writer    = CyberCSVWriter(config_manager, self.cyber_queue)

        # --- WindowManager (replaces direct CyberFeatureExtractor calls) ---
        # Owns the CyberFeatureExtractor internally; produces windowed rows.
        self.window_manager = WindowManager(
            config_manager=config_manager,
            connection_manager=self.connection_manager,
            cyber_queue=self.cyber_queue,
            logger=logger,
        )

        # --- Validation thread ---
        self.running = True
        self.validation_thread = threading.Thread(
            target=self._validation_worker,
            name="ValidationThread",
            daemon=True,
        )
        self.validation_thread.start()

    # ------------------------------------------------------------------
    # Public interface (called by PacketReceiver threads)
    # ------------------------------------------------------------------

    def process_raw_packet(
        self,
        data: bytes,
        src_ip: str,
        dst_ip: str,
        src_port: int,
        dst_port: int,
        arrival_time: float,
    ) -> None:
        """
        Accept a raw packet from a PacketReceiver and enqueue for validation.

        This method is called from PacketReceiver threads and must be fast.
        It does NO processing — only a non-blocking queue put.

        Args:
            data         : Raw bytes received from the TCP socket.
            src_ip       : Source IP of the ESP32.
            dst_ip       : Destination IP (server).
            src_port     : Ephemeral source port.
            dst_port     : Server listening port.
            arrival_time : Server-side Unix timestamp (time.time()).
        """
        try:
            self.validation_queue.put_nowait(
                (data, src_ip, dst_ip, src_port, dst_port, arrival_time)
            )
        except queue.Full:
            self.logger.log(
                "Validation queue full. Packet dropped.",
                severity="ERROR",
            )

    # ------------------------------------------------------------------
    # Validation worker (Thread 2)
    # ------------------------------------------------------------------

    def _validation_worker(self) -> None:
        """
        Continuously dequeue raw packets, parse them, and route to downstream systems.

        Valid packets → PhysicalCSVWriter queue + WindowManager.
        Invalid packets (with identifiable node_id) → WindowManager only.
        """
        while self.running or not self.validation_queue.empty():
            try:
                (data, src_ip, dst_ip,
                 src_port, dst_port, arrival_time) = self.validation_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                self._process_one_packet(
                    data, src_ip, dst_ip, src_port, dst_port, arrival_time
                )
            except Exception as e:
                self.logger.log(
                    f"Validation worker unhandled error: {e}",
                    severity="ERROR",
                )
            finally:
                self.validation_queue.task_done()

    def _process_one_packet(
        self,
        data: bytes,
        src_ip: str,
        dst_ip: str,
        src_port: int,
        dst_port: int,
        arrival_time: float,
    ) -> None:
        """
        Parse, validate, and route a single raw packet.

        Called exclusively from _validation_worker (single thread),
        so ConnectionStateManager NodeState fields are accessed safely.
        """
        parsed = self.parser.parse(data)
        node_id = parsed.get("node_id", -1) if parsed else -1

        if parsed and parsed.get("valid", False):
            # -------------------------------------------------------
            # VALID PACKET PATH
            # -------------------------------------------------------
            self.logger.log(
                f"Packet received: Node={node_id}, Seq={parsed.get('seq')}",
                node_id=str(node_id),
            )

            # Compute per-packet metrics and update session state
            node_state = self.connection_manager.get_or_create(node_id)
            metrics    = node_state.compute_packet_metrics(
                seq=parsed["seq"],
                size=parsed["raw_length"],
                arrival_time=arrival_time,
            )

            # Attach server-side arrival time for PhysicalCSVWriter timestamp
            parsed["arrival_time"] = arrival_time

            # Build a fully-populated PacketEntry for the WindowManager
            entry = PacketEntry(
                arrival_time          = arrival_time,
                node_id               = node_id,
                src_ip                = src_ip,
                dst_ip                = dst_ip,
                src_port              = src_port,
                dst_port              = dst_port,
                size                  = parsed["raw_length"],
                seq                   = parsed["seq"],
                inter_arrival_time    = metrics["inter_arrival_time"],
                seq_gap               = metrics["seq_gap"],
                is_duplicate          = metrics["is_duplicate"],
                is_out_of_order       = metrics["is_out_of_order"],
                is_valid              = True,
                crc_pass              = True,
                connection_start_time = metrics["connection_start_time"],
            )

            # Route to PhysicalCSVWriter
            try:
                self.physical_queue.put_nowait(parsed)
            except queue.Full:
                self.logger.log("Physical queue full. Physical row dropped.", severity="ERROR")

            # Route to WindowManager (buffered, flushed every 2 s)
            self.window_manager.add_packet(entry)

        else:
            # -------------------------------------------------------
            # INVALID PACKET PATH
            # -------------------------------------------------------
            err_msg = (
                parsed.get("error", "Unknown error") if parsed else "Parse failed"
            )

            if err_msg == "CRC mismatch":
                self.logger.log(
                    f"CRC failure. Node={node_id}",
                    severity="WARNING",
                    node_id=str(node_id),
                )
            else:
                self.logger.log(
                    f"Malformed packet rejected: {err_msg}",
                    severity="WARNING",
                    node_id=str(node_id),
                )

            # Forward invalid packets to WindowManager so integrity features
            # (crc_failure_count, invalid_packet_count) are counted accurately.
            # Packets with node_id == -1 cannot be associated with any node window
            # and are silently discarded by WindowManager.add_packet().
            if node_id >= 0:
                crc_ok = (err_msg != "CRC mismatch")
                invalid_entry = PacketEntry(
                    arrival_time          = arrival_time,
                    node_id               = node_id,
                    src_ip                = src_ip,
                    dst_ip                = dst_ip,
                    src_port              = src_port,
                    dst_port              = dst_port,
                    size                  = len(data),
                    seq                   = -1,      # Unknown for invalid packets
                    inter_arrival_time    = 0.0,
                    seq_gap               = 0,
                    is_duplicate          = False,
                    is_out_of_order       = False,
                    is_valid              = False,
                    crc_pass              = crc_ok,
                    connection_start_time = None,    # Not available for invalid packets
                )
                self.window_manager.add_packet(invalid_entry)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """
        Perform a graceful shutdown in dependency order:
          1. Stop the validation thread (no more packet processing).
          2. Stop the WindowManager (flush remaining buffered packets to cyber_queue).
          3. Stop the writers (drain their queues and close files).
        """
        self.running = False
        self.validation_thread.join()

        # WindowManager must be stopped BEFORE CyberCSVWriter so that any
        # partial windows are pushed to cyber_queue before the writer exits.
        self.window_manager.stop()

        self.physical_writer.stop()
        self.cyber_writer.stop()
