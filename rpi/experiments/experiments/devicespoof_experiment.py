"""
=============================================================================
 devicespoof_experiment.py
 Structural stub for the DeviceSpoof cybersecurity experiment.
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

def _build_spoof_packet(seq: int, node_id: int, ts_ms: int = 0) -> bytes:
    """Build a structurally valid 126-byte packet with a forged node_id."""
    body = struct.pack(
        _PACKET_FMT,
        0xABCD, 1, node_id, seq, ts_ms,
        *([0.0] * 27),
    )
    crc = _crc16_ccitt(body)
    return body + struct.pack("<H", crc)
class DeviceSpoofExperiment(BaseExperiment):
    """
    Evaluates the device identity validation capabilities of the cyber intrusion
    detection system by impersonating a legitimate IIoT edge device through
    controlled identity manipulation at the application layer.

    This experiment transmits structurally valid packets using a forged node_id
    field that matches a known legitimate device, while transmitting from an
    unauthorised source IP or port. The goal is to determine whether the IDS can
    distinguish spoofed device traffic from legitimate sensor data using IP/identity
    consistency features.

    Scientific purpose:
        Assess whether the combination of src_ip, node_id, and statistical
        feature distributions (timing, sequence continuity) are sufficient to
        identify device spoofing. A spoofed device may produce structurally valid
        packets but will lack the statistical consistency of a real physical sensor.

    Framework integration:
        The ExperimentManager automatically assigns the 'DeviceSpoofExperiment'
        label to all EdgeNode windows captured during the run() phase via the
        LabelManager. Dataset archival is performed automatically by the
        DatasetSynchronizer after cleanup() completes.
    """

    def initialize(self) -> None:
        cfg = self.config.get("devicespoof", {})
        self.interval = cfg.get("interval_ms", 200) / 1000.0
        self.spoofed_node_id = cfg.get("spoofed_node_id", 99)
        self.target_ip = self.config.get("server_ip", "127.0.0.1")
        self.target_port = self.config.get("server_port", 9000)
        self.sent_count = 0
        self.sock = None
        self._log_initialized()

    def run(self) -> None:
        self._log_started()
        
        pre_attack = self.experiment_config.get("pre_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing pre-attack baseline for {pre_attack}s...")
        time.sleep(pre_attack)

        attack_duration = self.experiment_config.get("attack_duration", 30.0)
        self.logger.info(f"[{self.name}] Starting Device Spoof Attack (Impersonating Node {self.spoofed_node_id}) against {self.target_ip}:{self.target_port}")
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.target_ip, self.target_port))

        start_time = time.time()
        seq_num = 3000
        
        while time.time() - start_time < attack_duration:
            pkt = _build_spoof_packet(
                seq=seq_num,
                node_id=self.spoofed_node_id,
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
        self.logger.info(f"[{self.name}] Device Spoof Attack complete. Sent: {self.sent_count}")
        self._log_cleaned_up()
