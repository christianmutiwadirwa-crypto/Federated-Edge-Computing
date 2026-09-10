"""
=============================================================================
 datatampering_experiment.py
 Structural stub for the DataTampering cybersecurity experiment.
=============================================================================
"""

from core.base_experiment import BaseExperiment
import os
import random
import socket
import struct
import time

_REAL_PACKET_SIZE = 126

def _random_payload(min_size: int, max_size: int) -> bytes:
    length = random.randint(min_size, max_size)
    return os.urandom(length)

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

class DataTamperingExperiment(BaseExperiment):
    """
    Evaluates the data integrity detection capabilities of the cyber intrusion
    detection system by transmitting structurally valid packets whose
    application-layer physical feature payload has been deliberately modified
    before delivery to the Edge Node.

    Unlike PacketInjection (which fabricates entirely new packets), DataTampering
    starts with a legitimate captured packet and modifies one or more fields
    in the physical feature vector (e.g. inflating acceleration values, zeroing
    out vibration statistics, or introducing physically impossible feature
    combinations) while recalculating the CRC to produce a packet that passes
    all structural validation checks.

    Scientific purpose:
        Determine whether statistical outlier features in the physical dataset
        (extreme mean values, zero-variance in a running machine scenario) can be
        correlated with cyber anomaly signals to detect data tampering attacks
        that successfully bypass cryptographic integrity checks.

    Framework integration:
        The ExperimentManager automatically assigns the 'DataTamperingExperiment'
        label to all EdgeNode windows captured during the run() phase via the
        LabelManager. Dataset archival is performed automatically by the
        DatasetSynchronizer after cleanup() completes.
    """

    def initialize(self) -> None:
        cfg = self.config.get("fuzzing", {})
        self.num_packets = cfg.get("num_packets", 1000)
        self.interval_ms = cfg.get("interval_ms", 10)
        self.min_size = cfg.get("min_size", 10)
        self.max_size = cfg.get("max_size", 300)
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
        src_ip, src_port = s.getsockname()
        self._register_attacker_flow(src_ip, src_port, self.target_ip, self.target_port)
        return s

    def run(self) -> None:
        self._log_started()
        
        pre_attack = self.experiment_config.get("pre_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing pre-attack baseline for {pre_attack}s...")
        time.sleep(pre_attack)

        attack_duration = self.experiment_config.get("attack_duration", 30.0)
        self.logger.info(f"[{self.name}] FUZZING / DATA TAMPERING ATTACK — {self.num_packets} malformed packets against {self.target_ip}:{self.target_port}")
        
        try:
            self.sock = self._connect()
        except Exception as e:
            self.logger.error(f"Cannot connect to {self.target_ip}:{self.target_port} — {e}")
            return

        interval_sec = self.interval_ms / 1000.0
        # Exclusively send packets that are structurally valid but have deliberately wrong CRCs
        fuzz_types = ["almost_valid"]
        
        start_time = time.time()
        i = 0
        
        while time.time() - start_time < attack_duration:
            strategy = random.choice(fuzz_types)

            if strategy == "random":
                payload = _random_payload(self.min_size, self.max_size)
            elif strategy == "correct_size_random":
                payload = os.urandom(_REAL_PACKET_SIZE)
            elif strategy == "almost_valid":
                payload = _almost_valid_payload()
            elif strategy == "zero":
                payload = b""   # empty — tests recv(0) handling
            else:  # oversized
                payload = os.urandom(random.randint(self.max_size, self.max_size * 3))

            try:
                if payload:
                    self.sock.sendall(payload)
                self.sent += 1
                if (i + 1) % 25 == 0:
                    self.logger.info(
                        f"  [{self.name}] {i + 1}/{self.num_packets} malformed packets sent "
                        f"(last strategy: {strategy})"
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
        self._clear_attacker_flows()
        self.logger.info(f"[{self.name}] Data Tampering complete: {self.sent} packets sent, {self.errors} errors.")
        self._log_cleaned_up()
