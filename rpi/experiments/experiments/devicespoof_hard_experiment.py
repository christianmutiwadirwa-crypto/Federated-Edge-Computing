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
class DeviceSpoofHardExperiment(BaseExperiment):
    """
    Evaluates the device identity validation capabilities of the cyber intrusion
    detection system under an aggressive spoofing scenario.

    This experiment transmits structurally valid packets using a forged node_id
    field that matches a known legitimate device, while transmitting from an
    unauthorised source IP or port. Unlike the baseline spoofing attack, this
    "hard" variant spams high-frequency packets to purposefully ruin the sequence
    number tracking and inter-arrival time metrics of the legitimate ESP32.

    Scientific purpose:
        Determine if the IDS can detect when a legitimate device's sequence space
        and timing consistency is being actively polluted by a high-rate attacker.
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
class DeviceSpoofHardExperiment(BaseExperiment):
    """
    Evaluates the device identity validation capabilities of the cyber intrusion
    detection system under an aggressive spoofing scenario.

    This experiment transmits structurally valid packets using a forged node_id
    field that matches a known legitimate device, while transmitting from an
    unauthorised source IP or port. Unlike the baseline spoofing attack, this
    "hard" variant spams high-frequency packets to purposefully ruin the sequence
    number tracking and inter-arrival time metrics of the legitimate ESP32.

    Scientific purpose:
        Determine if the IDS can detect when a legitimate device's sequence space
        and timing consistency is being actively polluted by a high-rate attacker.
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
        src_ip, src_port = self.sock.getsockname()
        self._register_attacker_flow(src_ip, src_port, self.target_ip, self.target_port)

        # Spam packets much faster than normal legitimate rate (e.g. 50ms instead of 400ms)
        interval_sec = self.interval / 5.0 
        
        start_time = time.time()
        
        # Keep an internal spoofed sequence number that rapidly outpaces the real device
        spoof_seq = 0

        while time.time() - start_time < attack_duration:
            pkt = _build_spoof_packet(
                seq=spoof_seq, 
                node_id=self.spoofed_node_id,
                ts_ms=int(time.time() * 1000)
            )

            try:
                self.sock.sendall(pkt)
                self.sent_count += 1
            except Exception as e:
                self.logger.error(f"  [{self.name}] Send error on packet: {e}")
                break

            time.sleep(interval_sec)
            spoof_seq += 10 # Rapidly jump sequence numbers to disrupt tracking

        post_attack = self.experiment_config.get("post_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing post-attack baseline for {post_attack}s...")
        time.sleep(post_attack)
        
        self._log_completed()

    def cleanup(self) -> None:
        if self.sock:
            self.sock.close()
        self._clear_attacker_flows()
        self.sent = self.sent_count
        self.logger.info(f"[{self.name}] Hard Device Spoof complete. Sent: {self.sent}")
        self._log_cleaned_up()
