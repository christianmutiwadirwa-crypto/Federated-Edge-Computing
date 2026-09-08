"""
=============================================================================
 truedatatampering_experiment.py
 True Data Tampering cybersecurity experiment.
=============================================================================
"""

from core.base_experiment import BaseExperiment
import os
import random
import socket
import struct
import time

_REAL_PACKET_SIZE = 126

def _almost_valid_payload() -> bytes:
    magic   = 0xABCD
    version = 1
    node_id = random.randint(0, 255)
    seq     = random.randint(0, 0xFFFFFF)
    ts_ms   = int(time.time() * 1000)
    floats  = [random.uniform(-50, 50) for _ in range(27)]
    body    = struct.pack("<HBBIQfffffffffffffffffffffffffff",
                          magic, version, node_id, seq, ts_ms, *floats)
    wrong_crc = random.randint(0x0000, 0xFFFF)
    return body + struct.pack("<H", wrong_crc)

class TrueDataTamperingExperiment(BaseExperiment):
    """
    Evaluates the data integrity detection capabilities of the cyber intrusion
    detection system by transmitting ONLY structurally valid packets whose
    application-layer physical feature payload has been deliberately modified
    (invalid CRC). 
    
    This guarantees that every window contains corrupt packets, bypassing the 
    noise-cleaning filters that drop windows with 0 crc failures.
    """

    def initialize(self) -> None:
        cfg = self.config.get("fuzzing", {})
        self.num_packets = cfg.get("num_packets", 1000)
        self.interval_ms = cfg.get("interval_ms", 100)
        self.target_ip = self.config.get("server_ip", "127.0.0.1")
        self.target_port = self.config.get("server_port", 9000)
        self.sent = 0
        self.errors = 0
        self.sock = None
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

        attack_duration = self.experiment_config.get("attack_duration", 431.0) # Default to 431s for ~200 windows
        self.logger.info(f"[{self.name}] TRUE DATA TAMPERING ATTACK — against {self.target_ip}:{self.target_port}")
        
        try:
            self.sock = self._connect()
        except Exception as e:
            self.logger.error(f"Cannot connect to {self.target_ip}:{self.target_port} — {e}")
            return

        interval_sec = self.interval_ms / 1000.0
        
        start_time = time.time()
        i = 0
        
        while time.time() - start_time < attack_duration:
            payload = _almost_valid_payload()

            try:
                if payload:
                    self.sock.sendall(payload)
                self.sent += 1
                if (i + 1) % 50 == 0:
                    self.logger.info(
                        f"  [{self.name}] {self.sent} true tampered packets sent"
                    )
            except (BrokenPipeError, ConnectionResetError):
                self.errors += 1
                self.logger.warning(f"  [{self.name}] Connection reset — reopening socket")
                try:
                    if self.sock:
                        self.sock.close()
                    self.sock = self._connect()
                except Exception as ce:
                    self.logger.error(f"  [{self.name}] Reconnect failed: {ce}")
                    break
            except Exception as e:
                self.errors += 1
                self.logger.warning(f"  [{self.name}] Send error: {e}")

            time.sleep(interval_sec)
            i += 1
        
        post_attack = self.experiment_config.get("post_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing post-attack baseline for {post_attack}s...")
        time.sleep(post_attack)
        
        self._log_completed()

    def cleanup(self) -> None:
        if self.sock:
            self.sock.close()
        self.logger.info(f"[{self.name}] True Data Tampering complete: {self.sent} packets sent, {self.errors} errors.")
        self._log_cleaned_up()
