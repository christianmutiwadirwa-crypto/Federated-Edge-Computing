"""
=============================================================================
 delay_experiment.py
 Structural stub for the Delay (Network Latency) cybersecurity experiment.
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

def _build_delay_packet(seq: int, node_id: int = 1, ts_ms: int = 0) -> bytes:
    """Build a structurally valid 126-byte packet accepted by PacketParser."""
    body = struct.pack(
        _PACKET_FMT,
        0xABCD, 1, node_id, seq, ts_ms,
        *([0.0] * 27),
    )
    crc = _crc16_ccitt(body)
    return body + struct.pack("<H", crc)
class DelayExperiment(BaseExperiment):
    """
    Evaluates the network latency attack detection capabilities of the cyber
    intrusion detection system by inserting controlled artificial transmission
    delays between consecutive packets in the IIoT data stream.

    By precisely controlling the sleep interval between transmissions, this
    experiment shifts the inter-arrival time distribution away from the normal
    operating baseline established by the legitimate ESP32 2-second sampling cycle.

    Scientific purpose:
        Determine whether the timing features extracted per 2-second window
        (mean_interarrival_time, std_interarrival_time, max_interarrival_time)
        are sensitive enough to identify network latency anomalies. Assess whether
        intentional delay injection can cause the CyberFeatureExtractor to assign
        a window to the wrong 2-second observation boundary.

    Framework integration:
        The ExperimentManager automatically assigns the 'DelayExperiment' label
        to all EdgeNode windows captured during the run() phase via the LabelManager.
        Dataset archival is performed automatically by the DatasetSynchronizer after
        cleanup() completes.
    """

    def initialize(self) -> None:
        cfg = self.config.get("delay", {})
        self.max_jitter_ms = cfg.get("max_jitter_ms", 500)
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
        self.logger.info(f"[{self.name}] Starting Delay Attack (Jitter up to {self.max_jitter_ms}ms) against {self.target_ip}:{self.target_port}")
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.target_ip, self.target_port))
        src_ip, src_port = self.sock.getsockname()
        self._register_attacker_flow(src_ip, src_port, self.target_ip, self.target_port)

        start_time = time.time()
        seq_num = 2000
        node_id = self.config.get("delay", {}).get("fake_node_id", 1)
        
        while time.time() - start_time < attack_duration:
            # Add randomized delay — this is the actual attack signal
            jitter = random.uniform(0, self.max_jitter_ms / 1000.0)
            time.sleep(0.1 + jitter)

            pkt = _build_delay_packet(
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
        
        post_attack = self.experiment_config.get("post_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing post-attack baseline for {post_attack}s...")
        time.sleep(post_attack)
        
        self._log_completed()

    def cleanup(self) -> None:
        if self.sock:
            self.sock.close()
        self._clear_attacker_flows()
        self.logger.info(f"[{self.name}] Delay Attack complete. Sent: {self.sent_count}")
        self._log_cleaned_up()
