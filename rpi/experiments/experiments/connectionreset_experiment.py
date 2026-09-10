"""
=============================================================================
 connectionreset_experiment.py
 Structural stub for the ConnectionReset cybersecurity experiment.
=============================================================================
"""

from core.base_experiment import BaseExperiment
import socket
import struct
import time

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

def _build_handshake_packet(node_id: int) -> bytes:
    """
    Build a single minimal valid packet carrying the target node_id.
    Sending this before immediately closing the connection forces the
    Edge Node's ConnectionStateManager to associate the disconnect with
    a known node, making reconnection_count visible in the dataset.
    """
    body = struct.pack(
        _PACKET_FMT,
        0xABCD, 1, node_id, 0, 0,
        *([0.0] * 27),
    )
    crc = _crc16_ccitt(body)
    return body + struct.pack("<H", crc)

class ConnectionResetExperiment(BaseExperiment):
    """
    Evaluates the detection capabilities of the cyber intrusion detection system
    against repeated rapid TCP connection establishment and termination events
    directed at the Edge Node server.

    This experiment simulates a pattern where an attacker (or malfunctioning device)
    continuously opens and immediately closes TCP connections without transmitting
    legitimate sensor data, causing the Edge Node's ConnectionStateManager to
    register elevated reconnection_count values per observation window.

    Scientific purpose:
        Determine whether the reconnection_count feature extracted per 2-second
        window provides sufficient signal to identify connection reset storms.
        Assess the interaction between connection_duration, reconnection_count,
        and total_packets in characterising this attack pattern.

    Framework integration:
        The ExperimentManager automatically assigns the 'ConnectionResetExperiment'
        label to all EdgeNode windows captured during the run() phase via the
        LabelManager. Dataset archival is performed automatically by the
        DatasetSynchronizer after cleanup() completes.
    """

    def initialize(self) -> None:
        cfg = self.config.get("connectionreset", {})
        self.interval = cfg.get("interval_ms", 100) / 1000.0
        self.target_ip = self.config.get("server_ip", "127.0.0.1")
        self.target_port = self.config.get("server_port", 9000)
        # node_id must match the legitimate ESP32's node_id so the Edge Node
        # associates each dropped connection with the correct NodeState.
        self.node_id = cfg.get("target_node_id", 1)
        self.count = 0
        self._log_initialized()

    def run(self) -> None:
        self._log_started()
        
        pre_attack = self.experiment_config.get("pre_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing pre-attack baseline for {pre_attack}s...")
        time.sleep(pre_attack)

        attack_duration = self.experiment_config.get("attack_duration", 30.0)
        self.logger.info(f"[{self.name}] Starting Connection Reset storm against {self.target_ip}:{self.target_port}")
        
        start_time = time.time()
        handshake_pkt = _build_handshake_packet(self.node_id)

        while time.time() - start_time < attack_duration:
            try:
                # Open connection
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                s.connect((self.target_ip, self.target_port))
                src_ip, src_port = s.getsockname()
                self._register_attacker_flow(src_ip, src_port, self.target_ip, self.target_port)
                
                # Send one valid handshake packet so the Edge Node registers
                # this as a connection from node_id before we drop it.
                s.sendall(handshake_pkt)
                
                # Immediately close (RST / FIN) — this is the attack event
                s.close()
                self.count += 1
            except Exception:
                pass
            
            time.sleep(self.interval)
        
        post_attack = self.experiment_config.get("post_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing post-attack baseline for {post_attack}s...")
        time.sleep(post_attack)
        
        self._log_completed()

    def cleanup(self) -> None:
        self._clear_attacker_flows()
        self.logger.info(f"[{self.name}] Connection Reset complete. Cycled {self.count} times.")
        self._log_cleaned_up()
