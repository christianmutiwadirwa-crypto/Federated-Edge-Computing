#!/usr/bin/env python3
"""
=============================================================================
 Cybersecurity Experiment Framework - IIoT Research Testbed
=============================================================================
 A modular framework designed to orchestrate authorized cyber-physical 
 experiments and generate highly reproducible, labeled datasets for 
 machine learning models in predictive maintenance systems.
=============================================================================
"""

import sys
import signal
import argparse

from core.config_manager import ConfigManager
from core.logger import Logger
from core.experiment_manager import ExperimentManager

def graceful_shutdown(signum, frame):
    print("\n[!] Shutdown signal received. Framework aborted.")
    sys.exit(0)

def main():
    # Handle CTRL+C cleanly
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    parser = argparse.ArgumentParser(description="IIoT Cybersecurity Experiment Framework")
    parser.add_argument("--experiment", type=str, default=None,
                        help="Name of the experiment to run (e.g. Replay)")
    parser.add_argument("--config", type=str, default="config/config.json",
                        help="Path to framework configuration JSON file")
    
    args = parser.parse_args()

    # 1. Initialize Configuration
    try:
        config_manager = ConfigManager(args.config)
        # Override experiment from command line if provided
        if args.experiment:
            config_manager.config["experiment"] = args.experiment
    except Exception as e:
        print(f"CRITICAL: Failed to load configuration: {e}")
        sys.exit(1)

    # 2. Initialize Logger
    logger = Logger(config_manager)
    logger.info("=====================================================")
    logger.info(" Starting Cybersecurity Experiment Framework ")
    logger.info("=====================================================")

    # 3. Initialize & Execute Experiment Manager
    manager = ExperimentManager(
        config_manager=config_manager,
        logger=logger
    )
    
    try:
        manager.execute()
    except Exception as e:
        logger.error(f"Framework execution failed with an unhandled exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
