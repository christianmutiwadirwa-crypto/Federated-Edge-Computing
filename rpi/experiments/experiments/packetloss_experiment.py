"""
=============================================================================
 packetloss_experiment.py
 Structural stub for the PacketLoss cybersecurity experiment.
=============================================================================
"""

from core.base_experiment import BaseExperiment
import socket
import time
import struct
import random

_PACKET_FMT = "<HBBIQfffffffffffffffffffffffffff"

def _crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

def _build_packet(seq: int, node_id: int = 1, ts_ms: int = 0) -> bytes:
    """Build a structurally valid 126-byte packet accepted by PacketParser."""
    body = struct.pack(
        _PACKET_FMT,
        0xABCD, 1, node_id, seq, ts_ms,
        *([0.0] * 27),
    )
    crc = _crc16_ccitt(body)
    return body + struct.pack("<H", crc)
class PacketLossExperiment(BaseExperiment):
    """
    Evaluates the communication reliability detection capabilities of the cyber
    intrusion detection system by selectively dropping packets from the legitimate
    IIoT data stream to emulate both accidental communication failures and
    selective packet loss attacks.

    Controlled packet dropping creates observable sequence number gaps in the
    stream, which the CyberFeatureExtractor records as sequence_number_gap and
    contributes to packet_loss_rate within each 2-second observation window.

    Scientific purpose:
        Determine whether sequence-based reliability features (packet_loss_rate,
        sequence_number_gap) and volume features (total_packets, packet_rate) can
        distinguish controlled selective loss from normal network jitter, and identify
        the minimum loss ratio at which the anomaly becomes statistically detectable.

    Framework integration:
        The ExperimentManager automatically assigns the 'PacketLossExperiment' label
        to all EdgeNode windows captured during the run() phase via the LabelManager.
        Dataset archival is performed automatically by the DatasetSynchronizer after
        cleanup() completes.
    """

    def initialize(self) -> None:
        cfg = self.config.get("packetloss", {})
        self.interval = cfg.get("interval_ms", 200) / 1000.0
        self.drop_probability = cfg.get("drop_probability", 0.3)
        self.target_ip = self.config.get("server_ip", "127.0.0.1")
        self.target_port = self.config.get("server_port", 9000)
        self.sent_count = 0
        self.dropped_count = 0
        self.sock = None
        self._log_initialized()

    def run(self) -> None:
        self._log_started()
        
        pre_attack = self.experiment_config.get("pre_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing pre-attack baseline for {pre_attack}s...")
        time.sleep(pre_attack)

        attack_duration = self.experiment_config.get("attack_duration", 30.0)
        self.logger.info(f"[{self.name}] Starting Packet Loss simulation ({self.drop_probability*100}% drop rate) against {self.target_ip}:{self.target_port}")
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.target_ip, self.target_port))
        src_ip, src_port = self.sock.getsockname()
        self._register_attacker_flow(src_ip, src_port, self.target_ip, self.target_port)

        start_time = time.time()
        seq_num = 1000
        node_id = self.config.get("packetloss", {}).get("fake_node_id", 1)
        
        while time.time() - start_time < attack_duration:
            # Decide if this packet is "dropped" — skip seq_num so the Edge
            # Node sees a gap (seq_gap > 0) and increments packet_loss_rate.
            if random.random() < self.drop_probability:
                self.dropped_count += 1
                seq_num += 1  # Advance seq so the gap is observed on next send
                time.sleep(self.interval)
                continue

            pkt = _build_packet(
                seq=seq_num,
                node_id=node_id,
                ts_ms=int(time.time() * 1000),
            )

            try:
                self.sock.sendall(pkt)
                self.sent_count += 1
            except Exception as e:
                self.logger.warning(f"Failed to send: {e}")
                break

            seq_num += 1
            time.sleep(self.interval)
        
        post_attack = self.experiment_config.get("post_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing post-attack baseline for {post_attack}s...")
        time.sleep(post_attack)
        
        self._log_completed()

    def cleanup(self) -> None:
        if self.sock:
            self.sock.close()
        self._clear_attacker_flows()
        self.logger.info(f"[{self.name}] Packet Loss complete. Sent: {self.sent_count}, 'Dropped': {self.dropped_count}")
        self._log_cleaned_up()
