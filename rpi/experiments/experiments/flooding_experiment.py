"""
=============================================================================
 flooding_experiment.py
 Structural stub for the Flooding (Denial-of-Service) cybersecurity experiment.
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

def _build_flood_packet(seq: int, node_id: int = 1, ts_ms: int = 0) -> bytes:
    body = struct.pack(
        _PACKET_FMT,
        0xABCD, 1, node_id, seq, ts_ms,
        *([0.0] * 27),
    )
    crc = _crc16_ccitt(body)
    return body + struct.pack("<H", crc)

class FloodingExperiment(BaseExperiment):
    """
    Evaluates the denial-of-service detection capabilities of the cyber intrusion
    detection system by simulating a high-rate packet flooding event.

    This experiment generates a sustained burst of traffic directed at the Edge
    Node to overwhelm its processing pipeline and trigger anomaly detection based
    on features such as packet_rate, data_rate, burst_intensity, and
    mean_interarrival_time deviating sharply from normal operating baselines.

    Scientific purpose:
        Assess whether windowed traffic volume features (packet_rate, data_rate,
        burst_intensity) computed by the CyberFeatureExtractor are sufficient to
        detect sustained high-rate flooding conditions, and at what injection rate
        the anomaly becomes statistically separable from normal traffic.

    Framework integration:
        The ExperimentManager automatically assigns the 'FloodingExperiment' label
        to all EdgeNode windows captured during the run() phase via the LabelManager.
        Dataset archival is performed automatically by the DatasetSynchronizer after
        cleanup() completes.
    """

    def initialize(self) -> None:
        cfg = self.config.get("flood", {})
        self.pps_min = cfg.get("packets_per_second_min", 20)
        self.pps_max = cfg.get("packets_per_second_max", 100)
        self.target_ip = self.config.get("server_ip", "127.0.0.1")
        self.target_port = self.config.get("server_port", 9000)
        self.node_id = cfg.get("fake_node_id", 1)
        self.sock = None
        self.sent = 0
        self.errors = 0
        self._log_initialized()

    def _connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect((self.target_ip, self.target_port))
        s.settimeout(None)
        return s

    def run(self) -> None:
        self._log_started()
        
        pre_attack = self.experiment_config.get("pre_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing pre-attack baseline for {pre_attack}s...")
        time.sleep(pre_attack)

        attack_duration = self.experiment_config.get("attack_duration", 30.0)
        self.logger.info(f"[{self.name}] FLOOD ATTACK — {self.pps_min}-{self.pps_max} pkt/s against {self.target_ip}:{self.target_port}")
        
        try:
            self.sock = self._connect()
        except Exception as e:
            self.logger.error(f"Cannot connect to {self.target_ip}:{self.target_port} — {e}")
            return

        deadline = time.time() + attack_duration
        seq = 0
        last_log = time.time()
        
        while time.time() < deadline:
            pkt = _build_flood_packet(seq % 0xFFFFFFFF, node_id=self.node_id,
                                      ts_ms=int(time.time() * 1000))
            try:
                self.sock.sendall(pkt)
                self.sock.setblocking(False)
                try:
                    self.sock.recv(1)
                except BlockingIOError:
                    pass
                self.sock.setblocking(True)
                self.sent += 1
                seq += 1
            except Exception as e:
                self.errors += 1
                self.logger.warning(f"Flood send error (reconnecting): {e}")
                try:
                    if self.sock:
                        self.sock.close()
                    self.sock = self._connect()
                except Exception as ce:
                    self.logger.error(f"Reconnect failed: {ce}")
                    break

            current_pps = random.uniform(self.pps_min, self.pps_max)
            time.sleep(1.0 / current_pps)

            if time.time() - last_log >= 10:
                elapsed = attack_duration - (deadline - time.time())
                self.logger.info(
                    f"  [{self.name}] {self.sent} packets sent | {self.errors} errors | "
                    f"{elapsed:.0f}/{attack_duration}s elapsed"
                )
                last_log = time.time()
        
        post_attack = self.experiment_config.get("post_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing post-attack baseline for {post_attack}s...")
        time.sleep(post_attack)
        
        self._log_completed()

    def cleanup(self) -> None:
        if self.sock:
            self.sock.close()
        self.logger.info(f"[{self.name}] Flood complete: {self.sent} packets sent, {self.errors} errors.")
        self._log_cleaned_up()
