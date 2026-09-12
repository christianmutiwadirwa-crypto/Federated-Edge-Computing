"""
=============================================================================
 reconscan_experiment.py
 Implementation for the ReconScan cybersecurity experiment.
=============================================================================
"""

from core.base_experiment import BaseExperiment
import random
import socket
import time

class ReconScanExperiment(BaseExperiment):
    """
    Evaluates the reconnaissance detection capabilities of the cyber intrusion
    detection system by simulating a network port scan (e.g. nmap).

    The experiment rapidly attempts TCP connections across a wide range of
    random ports (both closed and open) on the Edge Node to see if the IDS
    can correlate the network-layer noise (high connection rates, short durations)
    with potential impending attacks or recognize the reconnaissance signature.

    Scientific purpose:
        Determine whether network topology discovery (scanning) produces a 
        detectable cyber anomaly signature, and whether this signature can be
        differentiated from legitimate high-frequency but persistent IIoT traffic.
    """

    def initialize(self) -> None:
        cfg = self.config.get("reconscan", {})
        self.scan_rate_ms = cfg.get("scan_rate_ms", 10)
        self.target_ip = self.config.get("server_ip", "127.0.0.1")
        self.target_port = self.config.get("server_port", 9000)
        self.sent = 0
        self.errors = 0
        self.socks = []
        self._log_initialized()

    def run(self) -> None:
        self._log_started()
        
        pre_attack = self.experiment_config.get("pre_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing pre-attack baseline for {pre_attack}s...")
        time.sleep(pre_attack)

        attack_duration = self.experiment_config.get("attack_duration", 30.0)
        self.logger.info(f"[{self.name}] RECON SCAN ATTACK — Scanning ports on {self.target_ip} for {attack_duration}s")
        
        interval_sec = self.scan_rate_ms / 1000.0
        start_time = time.time()

        while time.time() - start_time < attack_duration:
            # Pick a random port, heavily weighting the actual open port to generate some real connections
            if random.random() < 0.1:
                port = self.target_port
            else:
                port = random.randint(1024, 65535)

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.05) # Very short timeout for scanning
                result = s.connect_ex((self.target_ip, port))
                
                # If we successfully connected (like to port 9000), register it so the IDS sees the flow
                if result == 0:
                    src_ip, src_port = s.getsockname()
                    self._register_attacker_flow(src_ip, src_port, self.target_ip, port)
                    self.socks.append(s)
                else:
                    s.close()
                self.sent += 1
            except Exception as e:
                self.errors += 1

            time.sleep(interval_sec)
        
        post_attack = self.experiment_config.get("post_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing post-attack baseline for {post_attack}s...")
        time.sleep(post_attack)
        
        self._log_completed()

    def cleanup(self) -> None:
        for s in self.socks:
            try:
                s.close()
            except:
                pass
        self._clear_attacker_flows()
        self.logger.info(f"[{self.name}] Recon Scan complete. Attempts: {self.sent}, Errors: {self.errors}")
        self._log_cleaned_up()
