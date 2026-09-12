#!/usr/bin/env python3
import json
import os
import subprocess
import argparse
from pathlib import Path

def main():
    print("=====================================================")
    print(" Starting 10-Minute Normal Traffic Collection")
    print(" Destination: results/evaluation")
    print("=====================================================")

    base_config_path = Path("config/config.json")
    eval_config_path = Path("config/eval_normal_config.json")

    if not base_config_path.exists():
        print(f"[!] Error: Cannot find {base_config_path}")
        return

    # 1. Read base config
    with open(base_config_path, "r") as f:
        config_data = json.load(f)

    # 2. Modify config for 10-minute evaluation run
    config_data["results_dir"] = "results/evaluation"
    
    if "experiments" not in config_data:
        config_data["experiments"] = {}
        
    if "NormalExperiment" not in config_data["experiments"]:
        config_data["experiments"]["NormalExperiment"] = {}
        
    # 600 seconds = 10 minutes
    config_data["experiments"]["NormalExperiment"]["attack_duration"] = 600.0
    config_data["experiments"]["NormalExperiment"]["pre_attack_duration"] = 10.0
    config_data["experiments"]["NormalExperiment"]["post_attack_duration"] = 10.0

    # 3. Save temporary eval config
    with open(eval_config_path, "w") as f:
        json.dump(config_data, f, indent=4)

    # 4. Run the experiment
    print(f"\n[*] Launching NormalExperiment for ~10.3 minutes...")
    try:
        subprocess.run(
            ["python", "main.py", "--experiment", "Normal", "--config", str(eval_config_path)],
            check=True
        )
    except subprocess.CalledProcessError:
        print(f"[!] Error: NormalExperiment failed.")
    except KeyboardInterrupt:
        print("\n[!] Collection aborted by user.")

    # 5. Cleanup temporary config
    if eval_config_path.exists():
        eval_config_path.unlink()

    print("\n=====================================================")
    print(" Evaluation Data Collection Complete!")
    print(" The new Normal data is in: rpi/experiments/results/evaluation")
    print("=====================================================")

if __name__ == "__main__":
    main()
