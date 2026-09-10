"""
=============================================================================
 duplicatepacket_experiment.py
 Structural stub for the DuplicatePacket cybersecurity experiment.
=============================================================================
"""

from core.base_experiment import BaseExperiment
import socket
import time
import struct

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

def _build_duplicate_packet(seq: int, node_id: int = 1) -> bytes:
    """Build a structurally valid 126-byte packet to be replayed as a duplicate."""
    body = struct.pack(
        _PACKET_FMT,
        0xABCD, 1, node_id, seq, 0,
        *([0.0] * 27),
    )
    crc = _crc16_ccitt(body)
    return body + struct.pack("<H", crc)
class DuplicatePacketExperiment(BaseExperiment):
    """
    Evaluates the duplicate packet detection capabilities of the cyber intrusion
    detection system by selectively retransmitting previously seen packets to
    introduce artificially elevated duplicate counts into the observed data stream.

    Duplicate packet injection mimics the behaviour of a man-in-the-middle attacker
    who intercepts and re-sends legitimate packets, or of a malfunctioning transmitter
    caught in a retransmission loop.

    Scientific purpose:
        Determine whether the duplicate_packet_count feature extracted per 2-second
        window is sufficient to identify sustained duplicate injection at various
        rates. Assess whether the duplicate feature alone provides separability, or
        whether it must be combined with IAT and packet_rate features.

    Framework integration:
        The ExperimentManager automatically assigns the 'DuplicatePacketExperiment'
        label to all EdgeNode windows captured during the run() phase via the
        LabelManager. Dataset archival is performed automatically by the
        DatasetSynchronizer after cleanup() completes.
    """

    def initialize(self) -> None:
        cfg = self.config.get("duplicate", {})
        self.interval = cfg.get("interval_ms", 100) / 1000.0
        self.target_ip = self.config.get("server_ip", "127.0.0.1")
        self.target_port = self.config.get("server_port", 9000)
        self.sent_count = 0
        self.sock = None
        
        # Pre-build the duplicate packet once with a fixed seq_num.
        # Sending the same seq_num repeatedly triggers is_duplicate=True
        # in ConnectionStateManager.compute_packet_metrics().
        node_id = cfg.get("fake_node_id", 1)
        self.packet = _build_duplicate_packet(seq=4000, node_id=node_id)
        
        self._log_initialized()

    def run(self) -> None:
        self._log_started()
        
        pre_attack = self.experiment_config.get("pre_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing pre-attack baseline for {pre_attack}s...")
        time.sleep(pre_attack)

        attack_duration = self.experiment_config.get("attack_duration", 30.0)
        self.logger.info(f"[{self.name}] Starting Duplicate Packet Attack against {self.target_ip}:{self.target_port}")
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.target_ip, self.target_port))
        src_ip, src_port = self.sock.getsockname()
        self._register_attacker_flow(src_ip, src_port, self.target_ip, self.target_port)

        start_time = time.time()
        
        while time.time() - start_time < attack_duration:
            try:
                self.sock.sendall(self.packet)
                self.sent_count += 1
            except Exception as e:
                self.logger.warning(f"Failed to send: {e}")
                break

            time.sleep(self.interval)
        
        post_attack = self.experiment_config.get("post_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing post-attack baseline for {post_attack}s...")
        time.sleep(post_attack)
        
        self._log_completed()

    def cleanup(self) -> None:
        if self.sock:
            self.sock.close()
        self._clear_attacker_flows()
        self.logger.info(f"[{self.name}] Duplicate Packet Attack complete. Sent: {self.sent_count}")
        self._log_cleaned_up()
