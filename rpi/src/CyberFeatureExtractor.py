"""
=============================================================================
 CyberFeatureExtractor.py
 Stateless batch cyber feature extractor for one observation window.
=============================================================================
 Receives a completed list of PacketEntry objects representing a single
 2-second observation window and computes all 44 cyber features in the
 exact CSV column order.

 Design principles:
   - STATELESS: No instance variables are mutated during extract().
     The same instance can safely be called from multiple threads.
   - All features describe the CURRENT window only.
     No lifetime cumulative statistics are computed.
   - Invalid packets (crc_pass=False, is_valid=False) are included in
     total_packets but excluded from packet-size and timing statistics.
   - burst_intensity uses 100ms sub-interval bins (20 per 2s window)
     so that a single-bin burst flood produces a value >> 1.0.

 Feature groups and CSV column order:
   1.  Window Information    (window_id, window_start_time, window_end_time)
   2.  Identity              (node_id, src_ip, dst_ip, src_port, dst_port)
   3.  Traffic Volume        (total_packets, total_bytes, packet_rate, data_rate,
                              valid_packet_count, valid_packet_rate)
   4.  Packet Size Stats     (mean, std, min, max packet size)
   5.  Timing Features       (mean/std/min/max IAT, iat_range, connection_duration,
                              active_connection_span)
   6.  Reliability Features  (loss_rate, duplicate_count, OOO_count, seq_gap,
                              total_seq_gap, min_seq_gap, reconnection_count)
   7.  Integrity Features    (crc_failure_count/rate, invalid_count/rate,
                              partial_packet_count)
   8.  Behaviour Features    (burst_intensity, mean/std sequence increment,
                              unique_src_ports_count)
   9.  Label                 (AttackLabel)
=============================================================================
"""

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from SlidingWindow import PacketEntry

# Expected packet size for the ESP32 binary protocol.
# Packets shorter than this received from the socket are "partial" —
# a primary signal for SlowDoS (Slowloris) attacks.
_EXPECTED_PACKET_SIZE: int = 126

class CyberFeatureExtractor:
    """
    Stateless batch processor: computes all cyber features from a window's packets.

    Instantiated once in WindowManager and reused for every window flush.
    """

    # Sub-interval size for burst_intensity computation (seconds).
    # 20 × 100 ms = 2 s window.  Must match window_duration_sec for
    # the count of bins to be consistent.
    _BURST_BIN_SEC: float = 0.10

    def __init__(self, config_manager):
        """
        Args:
            config_manager: Provides window_duration_sec.
        """
        self._window_duration: float = config_manager.get("window_duration_sec", 2)
        base_dir = Path(config_manager.get("directories", {}).get("base", "EdgeNode"))
        self._attacker_flows_file = base_dir / "state" / "attacker_flows.json"

    # ------------------------------------------------------------------
    # Main extraction entry point
    # ------------------------------------------------------------------

    def extract(
        self,
        window_id: int,
        window_start: float,
        window_end: float,
        packets: List[PacketEntry],
        reconnection_count: int,
        attack_label: str = "Normal",
    ) -> dict:
        """
        Compute the complete 44-feature cyber vector for one observation window.

        Args:
            window_id          : Monotonically increasing window identifier.
            window_start       : Unix timestamp of the first packet in the window.
            window_end         : Unix timestamp when the window was flushed.
            packets            : All PacketEntry objects buffered during this window.
                                 May include both valid and invalid packets.
            reconnection_count : Number of TCP reconnection events during this window
                                 (obtained via NodeState.drain_reconnections()).

        Returns:
            Ordered dict with all 44 features + 'AttackLabel'.
        """
        # Actual elapsed duration of this window
        duration: float = max(window_end - window_start, 1e-9)

        # Partition packets by validity
        valid_pkts   = [p for p in packets if p.is_valid]
        invalid_pkts = [p for p in packets if not p.is_valid]
        crc_failed   = [p for p in packets if not p.crc_pass]
        n_total      = len(packets)

        # ------------------------------------------------------------------
        # 0. Dynamic Label Calculation
        # ------------------------------------------------------------------
        attack_label = "Normal"
        try:
            if self._attacker_flows_file.exists():
                flows_data = json.loads(self._attacker_flows_file.read_text(encoding="utf-8"))
                if flows_data:
                    # Collect all attacker source ports
                    attacker_ports = {f.get("src_port") for f in flows_data if f.get("src_port")}
                    # If any flow doesn't specify port, we could match by IP, but our out-of-band scripts supply src_port
                    
                    attacker_packet_count = sum(1 for p in packets if p.src_port in attacker_ports)
                    attack_packet_fraction = attacker_packet_count / n_total if n_total > 0 else 0.0
                    
                    if attack_packet_fraction >= 0.15:
                        # Use the experiment name from the first flow as the label
                        attack_label = flows_data[0].get("experiment", "Attack")
                    elif attack_packet_fraction > 0.0:
                        attack_label = "Ambiguous"
        except Exception as e:
            pass # Default to Normal if reading fails


        # ------------------------------------------------------------------
        # 3. Traffic Volume Features
        # ------------------------------------------------------------------
        total_bytes  = sum(p.size for p in valid_pkts)
        packet_rate  = n_total / duration
        data_rate    = total_bytes / duration

        # Valid packet count and rate (excludes malformed/CRC-failed)
        valid_packet_count = len(valid_pkts)
        valid_packet_rate  = valid_packet_count / duration

        # ------------------------------------------------------------------
        # 4. Packet Size Statistics  (valid packets only)
        # ------------------------------------------------------------------
        valid_sizes = [p.size for p in valid_pkts]
        mean_pkt_size = _safe_mean(valid_sizes)
        std_pkt_size  = _safe_stdev(valid_sizes)
        min_pkt_size  = min(valid_sizes) if valid_sizes else 0
        max_pkt_size  = max(valid_sizes) if valid_sizes else 0

        # ------------------------------------------------------------------
        # 5. Timing Features
        # ------------------------------------------------------------------
        # Inter-arrival times: only from valid packets where IAT > 0
        # (the first packet of a session has IAT = 0.0 and is excluded).
        iats = [p.inter_arrival_time for p in valid_pkts if p.inter_arrival_time > 0.0]
        mean_iat = _safe_mean(iats)
        std_iat  = _safe_stdev(iats)
        min_iat  = min(iats) if iats else 0.0
        max_iat  = max(iats) if iats else 0.0
        # IAT Range: spread of interarrival times. High range = jitter attack (Delay).
        iat_range = max_iat - min_iat

        # Connection duration: time from session start to window end.
        # connection_start_time is the same for all valid packets in a session.
        conn_start: Optional[float] = None
        for p in valid_pkts:
            if p.connection_start_time is not None:
                conn_start = p.connection_start_time
                break
        connection_duration = (window_end - conn_start) if conn_start is not None else 0.0

        # Active connection span: time between the FIRST and LAST packet in this
        # specific window (not the full session). Detects SlowDoS where a connection
        # stays open without sending for long periods.
        # Window Active Span: measures the time span of packets *within* this specific window.
        # This is distinct from connection_duration, which measures the entire TCP session lifetime.
        # Useful for detecting bursts that occur quickly and leave the rest of the window empty.
        if len(valid_pkts) >= 2:
            window_active_span = valid_pkts[-1].arrival_time - valid_pkts[0].arrival_time
        elif len(valid_pkts) == 1:
            window_active_span = 0.0
        else:
            window_active_span = duration  # Empty window — worst case

        # ------------------------------------------------------------------
        # 6. Reliability Features
        # ------------------------------------------------------------------
        # Packet loss rate using ONLY the current window's sequence gaps.
        #   missing_seqs     = sum of all gaps between consecutive seq numbers
        #   expected_seqs    = received + missing
        #   packet_loss_rate = missing / expected
        all_seq_gaps  = [p.seq_gap for p in valid_pkts if p.seq_gap > 0]
        missing_seqs  = sum(p.seq_gap for p in valid_pkts)
        expected_seqs = len(valid_pkts) + missing_seqs
        packet_loss_rate = missing_seqs / expected_seqs if expected_seqs > 0 else 0.0

        duplicate_count   = sum(1 for p in valid_pkts if p.is_duplicate)
        out_of_order_count = sum(1 for p in valid_pkts if p.is_out_of_order)
        
        duplicate_delays = [p.duplicate_delay_ms for p in valid_pkts if p.is_duplicate and p.duplicate_delay_ms >= 0.0]
        mean_duplicate_delay_ms = _safe_mean(duplicate_delays) if duplicate_delays else -1.0

        # Max single-packet gap (0 = no gaps)
        sequence_number_gap = max((p.seq_gap for p in valid_pkts), default=0)
        # Total cumulative gap across the window (measures overall packet loss volume)
        total_seq_gap = missing_seqs
        # Min non-zero gap (characterises loss pattern: uniform vs bursty)
        min_seq_gap = min(all_seq_gaps) if all_seq_gaps else 0

        # ------------------------------------------------------------------
        # 7. Integrity Features
        # ------------------------------------------------------------------
        crc_failure_count  = len(crc_failed)
        crc_failure_rate   = crc_failure_count / n_total if n_total > 0 else 0.0
        invalid_count      = len(invalid_pkts)
        invalid_rate       = invalid_count / n_total if n_total > 0 else 0.0

        # Partial packet count: packets where bytes_received < expected size.
        # Primary signal for SlowDoS (Slowloris) which sends incomplete payloads
        # to hold socket connections open without triggering CRC checks.
        partial_packet_count = sum(
            1 for p in packets
            if p.bytes_received < _EXPECTED_PACKET_SIZE
        )

        # ------------------------------------------------------------------
        # 8. Behaviour Features
        # ------------------------------------------------------------------
        burst_intensity = self._compute_burst_intensity(packets, window_start, window_end)

        # Sequence increments: computed over valid, in-order, non-duplicate packets.
        # Increment = current_seq - previous_seq.
        # Healthy traffic produces a constant increment of 1 (no gaps).
        # Skipped / injected sequences produce higher values.
        ordered = [
            p for p in valid_pkts
            if not p.is_duplicate and not p.is_out_of_order
        ]
        seq_increments = [
            ordered[i].seq - ordered[i - 1].seq
            for i in range(1, len(ordered))
        ]
        mean_seq_inc = _safe_mean(seq_increments)
        std_seq_inc  = _safe_stdev(seq_increments)

        # Unique source ports: count of distinct ephemeral ports in this window.
        # Normal ESP32 traffic uses a single persistent connection → count = 1.
        # Flooding and DeviceSpoof open many short connections → count >> 1.
        unique_src_ports = len(set(p.src_port for p in packets if p.src_port > 0))

        # ------------------------------------------------------------------
        # 9. Payload Plausibility Features (computed from physical floats)
        # ------------------------------------------------------------------
        # These features are specifically designed to catch attacks that pass
        # CRC validation but contain implausible physical payloads:
        #   DataTampering_CRCForged : valid CRC, but modified float values
        #   PacketInjection_Conformant : valid CRC, but physically impossible values
        #
        # Index map for payload_floats tuple (27 values):
        # [0-2]  mean_x/y/z   [3-5]  rms_x/y/z    [6-8]  std_x/y/z
        # [9-11] max_x/y/z    [12-14] min_x/y/z   [15-17] p2p_x/y/z
        # [18-20] skew_x/y/z  [21-23] kurt_x/y/z  [24-26] crf_x/y/z

        pf_list = [p.payload_floats for p in valid_pkts if p.payload_floats is not None]

        # Mean RMS magnitude across the window: sqrt(rms_x² + rms_y² + rms_z²) per packet.
        # A real sensor at rest ≈ 0.3-0.8g. Conformant injection uses 2.5-4.5g.
        if pf_list:
            rms_mags = []
            for pf in pf_list:
                rms_x, rms_y, rms_z = pf[3], pf[4], pf[5]
                rms_mags.append((rms_x**2 + rms_y**2 + rms_z**2) ** 0.5)
            payload_rms_magnitude = _safe_mean(rms_mags)
        else:
            payload_rms_magnitude = 0.0

        # Frozen payload count: packets whose float tuple is identical to the
        # immediately preceding packet. The CRCForged tampering proxy sends
        # identical modified payloads in a loop → high frozen count.
        # A real sensor always produces slightly varying readings.
        frozen_count = 0
        for i in range(1, len(pf_list)):
            if pf_list[i] == pf_list[i - 1]:
                frozen_count += 1
        payload_frozen_count = frozen_count

        # Cross-axis std: standard deviation of (rms_x, rms_y, rms_z) per packet,
        # then averaged across the window. For a real 3-axis sensor, this is
        # non-zero (gravity distributes across axes). For forged payloads using
        # a single generator or all-zeros, this is near zero.
        if pf_list:
            cross_axis_stds = []
            for pf in pf_list:
                rms_vals = [pf[3], pf[4], pf[5]]
                cross_axis_stds.append(_safe_stdev(rms_vals))
            payload_cross_axis_std = _safe_mean(cross_axis_stds)
        else:
            payload_cross_axis_std = 0.0

        # All-zeros count: packets where ALL 27 floats are exactly 0.0.
        # Our attack scripts currently use *([0.0]*27) as a placeholder.
        # Even a motionless real sensor produces small gravity-bias non-zero values.
        payload_all_zeros_count = sum(
            1 for pf in pf_list if all(v == 0.0 for v in pf)
        )

        # ------------------------------------------------------------------
        # 2. Identity  (take from first valid packet; fallback to any packet)
        # ------------------------------------------------------------------
        ref: PacketEntry = valid_pkts[0] if valid_pkts else packets[0]

        # ------------------------------------------------------------------
        # 1. Window timestamps (ISO 8601 UTC)
        # ------------------------------------------------------------------
        ws_str = _fmt_ts(window_start)
        we_str = _fmt_ts(window_end)

        # ------------------------------------------------------------------
        # Assemble feature dict in exact CSV column order
        # ------------------------------------------------------------------
        return {
            # --- Window Information ---
            "window_id":                 window_id,
            "window_start_time":         ws_str,
            "window_end_time":           we_str,

            # --- Identity ---
            "node_id":                   ref.node_id,
            "src_ip":                    ref.src_ip,
            "dst_ip":                    ref.dst_ip,
            "src_port":                  ref.src_port,
            "dst_port":                  ref.dst_port,

            # --- Traffic Volume ---
            "total_packets":             n_total,
            "total_bytes":               total_bytes,
            "packet_rate":               _r(packet_rate),
            "data_rate":                 _r(data_rate),
            "valid_packet_count":        valid_packet_count,
            "valid_packet_rate":         _r(valid_packet_rate),

            # --- Packet Size Statistics ---
            "mean_packet_size":          _r(mean_pkt_size),
            "std_packet_size":           _r(std_pkt_size),
            "min_packet_size":           min_pkt_size,
            "max_packet_size":           max_pkt_size,

            # --- Timing Features ---
            "mean_interarrival_time":    _r(mean_iat),
            "std_interarrival_time":     _r(std_iat),
            "min_interarrival_time":     _r(min_iat),
            "max_interarrival_time":     _r(max_iat),
            "iat_range":                 _r(iat_range),
            "connection_duration":       _r(connection_duration),
            "window_active_span":        _r(window_active_span),

            # --- Reliability Features ---
            "packet_loss_rate":          _r(packet_loss_rate),
            "duplicate_packet_count":    duplicate_count,
            "mean_duplicate_delay_ms":   _r(mean_duplicate_delay_ms),
            "out_of_order_packet_count": out_of_order_count,
            "sequence_number_gap":       sequence_number_gap,
            "total_seq_gap":             total_seq_gap,
            "min_seq_gap":               min_seq_gap,
            "reconnection_count":        reconnection_count,

            # --- Integrity Features ---
            "crc_failure_count":         crc_failure_count,
            "crc_failure_rate":          _r(crc_failure_rate),
            "invalid_packet_count":      invalid_count,
            "invalid_packet_rate":       _r(invalid_rate),
            "partial_packet_count":      partial_packet_count,

            # --- Behaviour Features ---
            "burst_intensity":           _r(burst_intensity),
            "mean_sequence_increment":   _r(mean_seq_inc),
            "std_sequence_increment":    _r(std_seq_inc),
            "unique_src_ports_count":    unique_src_ports,

            # --- Payload Plausibility Features ---
            "payload_rms_magnitude":     _r(payload_rms_magnitude),
            "payload_frozen_count":      payload_frozen_count,
            "payload_cross_axis_std":    _r(payload_cross_axis_std),
            "payload_all_zeros_count":   payload_all_zeros_count,

            # --- Label ---
            "AttackLabel":               attack_label,
        }

    # ------------------------------------------------------------------
    # Burst intensity helper
    # ------------------------------------------------------------------

    def _compute_burst_intensity(
        self,
        packets: List[PacketEntry],
        window_start: float,
        window_end: float,
    ) -> float:
        """
        Quantify how concentrated packet arrivals are within the window.

        Method:
            Divide the window into _BURST_BIN_SEC-wide bins.
            Count packets per bin.
            burst_intensity = max(bin_counts) / mean(bin_counts)

        Interpretation:
            1.0  → perfectly uniform arrival pattern
            20.0 → all packets in one 100ms bin (maximum burst for 2s window)

        Returns:
            0.0 if fewer than 2 packets (insufficient data for meaningful ratio).
        """
        if len(packets) < 2:
            return 0.0

        duration = window_end - window_start
        num_bins = max(1, int(duration / self._BURST_BIN_SEC))

        bin_counts = [0] * num_bins
        for p in packets:
            elapsed  = p.arrival_time - window_start
            # Add tiny epsilon to prevent float truncation (e.g. 0.3/0.1=2.999999 -> 2)
            bin_idx  = int((elapsed + 1e-9) / self._BURST_BIN_SEC)
            bin_idx  = max(0, min(bin_idx, num_bins - 1))  # clamp to valid range
            bin_counts[bin_idx] += 1

        # Use ALL bins (including zeros) so a single-bin burst yields a high value.
        mean_count = sum(bin_counts) / len(bin_counts)
        if mean_count == 0.0:
            return 0.0

        return max(bin_counts) / mean_count


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _safe_mean(values: list) -> float:
    """Return mean of values, or 0.0 if list is empty."""
    return statistics.mean(values) if values else 0.0


def _safe_stdev(values: list) -> float:
    """Return sample standard deviation, or 0.0 if fewer than 2 values."""
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _r(value: float, ndigits: int = 6) -> float:
    """Round a float to ndigits decimal places for clean CSV output."""
    return round(value, ndigits)


def _fmt_ts(unix_ts: float) -> str:
    """Format a Unix timestamp as ISO 8601 UTC string."""
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )

