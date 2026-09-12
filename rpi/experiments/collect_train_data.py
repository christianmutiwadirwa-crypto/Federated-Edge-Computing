#!/usr/bin/env python3
import json
import os
import subprocess
import argparse
from pathlib import Path

# Batch 1 (7 classes)
BATCH_1 = [
    "NormalExperiment",
    # "FloodingExperiment",
   # "SlowDoSExperiment",
    "PacketInjectionMalformedExperiment",
    "PacketInjectionConformantExperiment",
    #"PacketLossExperiment",
   # "DuplicatePacketExperiment"
]

# Batch 2 (7 classes)
BATCH_2 = [
    "DelayExperiment",
    "ConnectionResetExperiment",
    "ReconScanExperiment",
    "DeviceSpoofHardExperiment",
    "DataTamperingBitFlipExperiment",
    "DataTamperingCRCForgedExperiment",
    "ReplayExperiment"
]

def main():
    parser = argparse.ArgumentParser(description="Training Data Collection Orchestrator")
    parser.add_argument("--batch", type=int, choices=[1, 2], required=True, help="Batch number to run (1 or 2)")
    args = parser.parse_args()

    # Determine which batch to run
    batch_experiments = BATCH_1 if args.batch == 1 else BATCH_2
    
    config_path = Path("config/config.json")
    if not config_path.exists():
        print(f"[!] Error: Cannot find {config_path}")
        return

    # Read config to display info
    with open(config_path, "r") as f:
        config_data = json.load(f)

    print("=====================================================")
    print(f" Starting Training Data Collection (Batch {args.batch})")
    print(f" Total Experiments: {len(batch_experiments)}")
    print(f" Output Directory: rpi/experiments/results")
    print("=====================================================")

    # Run experiments sequentially
    for i, exp_key in enumerate(batch_experiments, 1):
        # We need the base experiment name without 'Experiment' suffix 
        # (e.g. 'ReplayExperiment' -> 'Replay' as expected by main.py arg)
        exp_name = exp_key.replace("Experiment", "")
        
        # Look up duration from config just to display to user
        exp_config = config_data.get("experiments", {}).get(exp_key, {})
        duration = exp_config.get("attack_duration", 1800.0)
        pre = exp_config.get("pre_attack_duration", 30.0)
        post = exp_config.get("post_attack_duration", 30.0)
        total_time_seconds = duration + pre + post
        total_time = total_time_seconds / 60.0
        
        print(f"\n[{i}/{len(batch_experiments)}] Running {exp_name} (~{total_time:.1f} mins)...")
        try:
            # Run main.py using standard config. 
            # Add a 5-minute safety buffer timeout to prevent overnight hanging.
            subprocess.run(
                ["python", "main.py", "--experiment", exp_name, "--config", str(config_path)],
                check=True,
                timeout=total_time_seconds + 300
            )
        except subprocess.CalledProcessError:
            print(f"[!] Error: Experiment {exp_name} failed. Continuing to next...")
        except subprocess.TimeoutExpired:
            print(f"[!] Critical: Experiment {exp_name} hung and timed out. Force killed. Continuing...")
        except KeyboardInterrupt:
            print("\n[!] Collection aborted by user.")
            break

    print("=====================================================")
    print(f" Batch {args.batch} Data Collection Complete!")
    print(" Data saved to: rpi/experiments/results")
    print("=====================================================")

if __name__ == "__main__":
    main()
