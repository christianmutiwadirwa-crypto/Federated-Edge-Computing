#!/usr/bin/env python3
"""
=============================================================================
 Cyber Attack Injection Framework - Industrial IoT
=============================================================================
 A modular framework designed to generate reproducible cyber attacks for
 building machine learning datasets in predictive maintenance systems.

 The attacker acts as an independent entity on the network, passively
 observing legitimate traffic and injecting malicious packets without
 modifying the original edge node firmware or receiver software.
=============================================================================
"""

import sys
import signal

from core.config_manager import ConfigManager
from core.logger import Logger
from core.network_manager import NetworkManager
from core.packet_capture import PacketCapture
from core.packet_sender import PacketSender
from core.attack_controller import AttackController

def graceful_shutdown(signum, frame):
    print("\n[!] Shutdown signal received. Exiting framework gracefully.")
    sys.exit(0)

def main():
    # Handle CTRL+C cleanly
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # 1. Initialize Configuration
    try:
        config_manager = ConfigManager("config/config.json")
    except Exception as e:
        print(f"CRITICAL: Failed to load configuration: {e}")
        sys.exit(1)

    # 2. Initialize Logger
    logger = Logger(config_manager)
    logger.info("Initializing Cyber Attack Injection Framework...")

    # 3. Initialize Core Network Components
    network_manager = NetworkManager(config_manager, logger)
    
    packet_capture = PacketCapture(
        network_manager=network_manager,
        logger=logger,
        bpf_filter=config_manager.get("bpf_filter", "tcp")
    )
    
    packet_sender = PacketSender(
        network_manager=network_manager,
        logger=logger
    )

    # 4. Initialize and Execute Attack Plugin
    controller = AttackController(
        config_manager=config_manager,
        logger=logger,
        network_manager=network_manager,
        packet_capture=packet_capture,
        packet_sender=packet_sender
    )
    
    try:
        controller.execute()
    except Exception as e:
        logger.error(f"Framework execution failed with an unhandled exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
