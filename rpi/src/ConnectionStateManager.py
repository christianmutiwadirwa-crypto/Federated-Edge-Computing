"""
=============================================================================
 ConnectionStateManager.py
 Session-level TCP connection state tracking for each connected ESP32 node.
=============================================================================
 Responsibilities:
   - Track the session start time (used to compute connection_duration).
   - Track the previous sequence number and arrival time so per-packet
     metrics (seq_gap, is_duplicate, is_out_of_order, inter_arrival_time)
     can be computed during packet validation.
   - Count reconnection events per observation window.

 Design notes:
   - connection_start_time uses a sentinel (None) so that the FIRST packet's
     arrival_time defines t=0, eliminating negative connection durations.
   - All per-packet computed metrics are returned from compute_packet_metrics()
     and embedded into PacketEntry objects. The WindowManager and
     CyberFeatureExtractor never read NodeState directly except for
     drain_reconnections(), which is thread-safe.
   - compute_packet_metrics() is called only from the single DataManager
     validation thread, so its fields do NOT require a lock.
     Only _pending_reconnections is accessed from two threads and is
     protected by its own lock.
=============================================================================
"""

import threading
from typing import Optional, Dict


# ---------------------------------------------------------------------------
# NodeState
# ---------------------------------------------------------------------------

class NodeState:
    """
    Session-level communication state for a single ESP32 node.

    Attributes:
        node_id                  : ESP32 node identifier.
        connection_start_time    : Unix timestamp of the first ever packet
                                   from this node. None until first packet.
        latest_sequence_number   : Highest confirmed sequence number seen.
                                   -1 before any packet is received.
        previous_arrival_timestamp: Arrival time of the previous packet.
                                   -1.0 before any packet is received.
    """

    def __init__(self, node_id: int):
        self.node_id: int = node_id

        # --- Connection lifetime tracking ---
        # Sentinel: set to arrival_time of the FIRST packet, not time.time().
        # This guarantees connection_duration >= 0.0 for all packets.
        self.connection_start_time: Optional[float] = None

        # --- Per-packet sequence tracking ---
        # Mutated only by compute_packet_metrics() (DataManager validation thread).
        self.latest_sequence_number: int  = -1
        self.previous_arrival_timestamp: float = -1.0
        
        # Track recent sequence timestamps for Duplicate vs Replay detection
        # Replays have huge delays, true duplicates are nearly immediate
        self._seen_seqs: Dict[int, float] = {}

        # --- Reconnection counter ---
        # Incremented by record_reconnection() which may be called from
        # PacketReceiver threads or the validation thread.
        # Drained by WindowManager timer thread at each window flush.
        # Protected by a dedicated lock.
        self._recon_lock            = threading.Lock()
        self._pending_reconnections: int = 0

    # ------------------------------------------------------------------
    # Reconnection tracking (thread-safe)
    # ------------------------------------------------------------------

    def record_reconnection(self) -> None:
        """
        Record that this node re-established a dropped TCP connection.

        Increments the pending reconnection counter (visible in the next
        window flush) and resets sequence tracking state so the new
        connection's sequence numbers are treated as a fresh stream.

        NOTE: connection_start_time is intentionally NOT reset here.
              It represents total session lifetime since first contact.
        """
        with self._recon_lock:
            self._pending_reconnections += 1
        # Reset sequence state — new connection has a new sequence stream.
        self.latest_sequence_number    = -1
        self.previous_arrival_timestamp = -1.0
        self._seen_seqs.clear()

    def drain_reconnections(self) -> int:
        """
        Return the number of reconnection events since the last drain, then reset.

        Called by WindowManager at each window flush to obtain the per-window
        reconnection count. After this call, the counter is zero until the
        next reconnection event occurs.

        Returns:
            int: Count of reconnection events in the elapsed window.
        """
        with self._recon_lock:
            count = self._pending_reconnections
            self._pending_reconnections = 0
            return count

    # ------------------------------------------------------------------
    # Per-packet metric computation (DataManager validation thread only)
    # ------------------------------------------------------------------

    def compute_packet_metrics(
        self,
        seq: int,
        size: int,
        arrival_time: float,
    ) -> dict:
        """
        Compute per-packet derived metrics and update session state.

        Must be called ONLY from the DataManager validation thread.
        Updates internal state (latest_sequence_number, previous_arrival_timestamp,
        connection_start_time) as a side effect.

        Args:
            seq          : Sequence number from the validated packet header.
            size         : Byte count of the raw packet.
            arrival_time : Server-side Unix timestamp of packet receipt.

        Returns:
            dict with keys:
              inter_arrival_time   (float): seconds since previous packet; 0.0 for first.
              seq_gap              (int)  : missing seqs before this packet; 0 if consecutive.
              is_duplicate         (bool) : True if seq == latest_sequence_number.
              is_out_of_order      (bool) : True if seq < latest_sequence_number.
              connection_start_time(float): Unix timestamp of session start (for PacketEntry).
              duplicate_delay      (float): seconds since this seq was first seen (-1.0 if not duplicate)
        """
        # --- Set session start on first packet ---
        if self.connection_start_time is None:
            self.connection_start_time = arrival_time

        # --- Inter-arrival time ---
        if self.previous_arrival_timestamp > 0.0:
            inter_arrival = arrival_time - self.previous_arrival_timestamp
        else:
            inter_arrival = 0.0  # First packet of this session

        # --- Sequence analysis ---
        is_duplicate    = False
        is_out_of_order = False
        seq_gap         = 0
        duplicate_delay = -1.0

        if self.latest_sequence_number != -1:
            if seq == self.latest_sequence_number:
                # Exact retransmission of the last seen seq
                is_duplicate = True
            elif seq < self.latest_sequence_number:
                # Arrived later than a higher seq already seen
                is_out_of_order = True
            elif seq > self.latest_sequence_number + 1:
                # Gap: one or more sequence numbers are missing
                seq_gap = seq - self.latest_sequence_number - 1

        # Calculate time since this exact sequence number was first seen
        if seq in self._seen_seqs:
            duplicate_delay = arrival_time - self._seen_seqs[seq]
        else:
            # Bound dictionary size to avoid memory leaks on long-running nodes
            if len(self._seen_seqs) > 50000:
                # Crude evict of oldest (Python 3.7+ dicts preserve insertion order)
                self._seen_seqs.pop(next(iter(self._seen_seqs)))
            self._seen_seqs[seq] = arrival_time

        # --- State update ---
        # Only advance latest_sequence_number for in-order, non-duplicate packets
        if not is_duplicate and not is_out_of_order:
            self.latest_sequence_number = seq
        self.previous_arrival_timestamp = arrival_time

        return {
            "inter_arrival_time":    inter_arrival,
            "seq_gap":               seq_gap,
            "is_duplicate":          is_duplicate,
            "is_out_of_order":       is_out_of_order,
            "connection_start_time": self.connection_start_time,
            "duplicate_delay":       duplicate_delay,
        }


# ---------------------------------------------------------------------------
# ConnectionStateManager
# ---------------------------------------------------------------------------

class ConnectionStateManager:
    """
    Thread-safe registry of per-node session states.

    Maintains one NodeState per connected node_id for the lifetime of the
    server process. NodeState objects are never deleted during normal operation
    (a disconnected node may reconnect at any time).
    """

    def __init__(self):
        self._lock: threading.Lock = threading.Lock()
        self._nodes: Dict[int, NodeState] = {}

    def get_or_create(self, node_id: int) -> NodeState:
        """
        Return the NodeState for node_id, creating one if it does not exist.

        Args:
            node_id: ESP32 node identifier.

        Returns:
            NodeState for the given node.
        """
        with self._lock:
            if node_id not in self._nodes:
                self._nodes[node_id] = NodeState(node_id)
            return self._nodes[node_id]

    def record_connection(self, node_id: int) -> None:
        """
        Called by TCPServer when a node establishes (or re-establishes) a connection.

        If the node is already known, increments its reconnection counter and
        resets sequence tracking. If the node is unknown, a NodeState will be
        created automatically when the first packet arrives.

        Args:
            node_id: ESP32 node identifier. -1 if unknown (pre-handshake).
        """
        if node_id < 0:
            return  # Cannot associate an unknown node
        with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].record_reconnection()
            # If node is not yet known, its NodeState will be created on
            # the first packet via get_or_create().
