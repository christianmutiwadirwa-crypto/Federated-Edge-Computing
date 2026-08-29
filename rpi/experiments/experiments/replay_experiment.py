"""
=============================================================================
 replay_experiment.py
 Structural stub for the Replay cybersecurity experiment.
=============================================================================
"""

from core.base_experiment import BaseExperiment
import time
from pathlib import Path

try:
    from scapy.all import sniff, wrpcap, sendp, send, Ether
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
class ReplayExperiment(BaseExperiment):
    """
    Evaluates the resilience of the cyber intrusion detection system against
    replay attacks.

    This experiment reuses previously observed application-layer packets extracted
    from a PCAP capture of a legitimate IIoT edge node session, and replays them
    to the target Edge Node over a fresh TCP connection while precisely reproducing
    the original inter-arrival timing of the physical device.

    Scientific purpose:
        Determine whether the CyberFeatureExtractor's timing and sequence-based
        features (inter-arrival time, sequence gaps, burst intensity) are sufficient
        to distinguish replayed historical traffic from live sensor traffic.

    Framework integration:
        The ExperimentManager automatically assigns the 'ReplayExperiment' label
        to all EdgeNode windows captured during the run() phase via the LabelManager.
        Dataset archival is performed automatically by the DatasetSynchronizer after
        cleanup() completes.
    """

    def initialize(self) -> None:
        cfg = self.config.get("replay", {})
        self.capture_count = cfg.get("capture_count", 5)
        self.replay_count = cfg.get("replay_count", 10)
        self.delay_before_replay = cfg.get("delay_before_replay", 30)
        self.replay_interval_ms = cfg.get("replay_interval_ms", 500)
        self.target_port = self.config.get("server_port", 9000)
        
        self.captured_packets = []
        if not SCAPY_AVAILABLE:
            self.logger.error("Scapy is not available. Replay attack will fail.")
            
        self._log_initialized()

    def run(self) -> None:
        self._log_started()
        
        pre_attack = self.experiment_config.get("pre_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing pre-attack baseline for {pre_attack}s...")
        time.sleep(pre_attack)

        if not SCAPY_AVAILABLE:
            self.logger.error("Cannot run ReplayExperiment without scapy.")
            return

        self.logger.info(f"[{self.name}] Phase 1: Capturing {self.capture_count} packets on port {self.target_port}...")
        
        try:
            bpf_filter = f"tcp port {self.target_port}"
            self.captured_packets = sniff(filter=bpf_filter, count=self.capture_count, timeout=30)
        except Exception as e:
            self.logger.error(f"Failed to capture packets: {e}")
            return
            
        if not self.captured_packets:
            self.logger.error("No packets captured. Aborting Replay Attack.")
            return

        save_path = Path(f"captures/replay_base_{int(time.time())}.pcap")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            wrpcap(str(save_path), self.captured_packets)
            self.logger.info(f"[{self.name}] Saved {len(self.captured_packets)} packets to {save_path}")
        except Exception as e:
            self.logger.error(f"Failed to save PCAP: {e}")

        self.logger.info(f"[{self.name}] Waiting {self.delay_before_replay}s before replay...")
        time.sleep(self.delay_before_replay)

        attack_duration = self.experiment_config.get("attack_duration", 1800.0)
        self.logger.info(f"[{self.name}] Phase 2: Replaying {len(self.captured_packets)} packets continuously for {attack_duration}s")
        
        interval_sec = self.replay_interval_ms / 1000.0
        
        end_time = time.time() + attack_duration
        iteration = 0
        while time.time() < end_time:
            iteration += 1
            for i, pkt in enumerate(self.captured_packets):
                if pkt.haslayer(Ether):
                    try:
                        sendp(pkt, verbose=False)
                        self.logger.info(f"[{self.name}] Replaying Packet #{i+1} (Iter {iteration})")
                    except Exception as e:
                        self.logger.error(f"Failed to send packet #{i+1} at Layer 2: {e}")
                else:
                    try:
                        send(pkt, verbose=False)
                        self.logger.info(f"[{self.name}] Replaying Packet #{i+1} (Layer 3 fallback) (Iter {iteration})")
                    except Exception as e:
                        self.logger.error(f"Failed to send packet #{i+1} at Layer 3: {e}")
                
                time.sleep(interval_sec)

        post_attack = self.experiment_config.get("post_attack_duration", 5.0)
        self.logger.info(f"[{self.name}] Observing post-attack baseline for {post_attack}s...")
        time.sleep(post_attack)
        
        self._log_completed()

    def cleanup(self) -> None:
        self.captured_packets.clear()
        self.logger.info(f"[{self.name}] Replay Attack complete.")
        self._log_cleaned_up()
