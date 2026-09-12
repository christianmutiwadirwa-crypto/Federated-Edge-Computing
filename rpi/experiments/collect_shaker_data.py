#!/usr/bin/env python3
import json
import os
import subprocess
import time
from pathlib import Path

def main():
    config_path = "config/config.json"
    shaker_config_path = "config/shaker_config.json"
    
    # 45 minutes = 2700 seconds
    duration_sec = 2700.0
    pre_duration = 30.0
    post_duration = 30.0
    
    print("=====================================================")
    print(" Starting Shaker (Physical Anomaly) Data Collection")
    print(f" Output Directory: results/shaker")
    print("=====================================================")
    
    # 1. Read existing config
    if not os.path.exists(config_path):
        print(f"[!] Error: Cannot find {config_path}")
        return
        
    with open(config_path, "r") as f:
        config_data = json.load(f)
        
    # 2. Modify config for shaker
    config_data["results_dir"] = "results/shaker"
    
    # We strictly only want the NormalExperiment for shaker baseline
    if "NormalExperiment" not in config_data.get("experiments", {}):
        print("[!] Error: NormalExperiment not found in config.")
        return
        
    config_data["experiments"]["NormalExperiment"]["pre_attack_duration"] = pre_duration
    config_data["experiments"]["NormalExperiment"]["attack_duration"] = duration_sec
    config_data["experiments"]["NormalExperiment"]["post_attack_duration"] = post_duration
    
    # 3. Write temp shaker config
    with open(shaker_config_path, "w") as f:
        json.dump(config_data, f, indent=4)
        
    print(f"[*] Generated temporary config at {shaker_config_path}")
    total_time_mins = (duration_sec + pre_duration + post_duration) / 60.0
    print(f"[*] Starting NormalExperiment on shaker for ~{total_time_mins:.1f} minutes...")
    
    # 4. Run experiment
    try:
        subprocess.run(
            ["python", "main.py", "--experiment", "Normal", "--config", shaker_config_path],
            check=True,
            timeout=duration_sec + 300
        )
    except subprocess.CalledProcessError:
        print("[!] Error: Shaker experiment failed.")
    except subprocess.TimeoutExpired:
        print("[!] Critical: Shaker experiment hung and timed out. Force killed.")
    except KeyboardInterrupt:
        print("\n[!] Collection aborted by user.")
            
    # 5. Cleanup
    if os.path.exists(shaker_config_path):
        os.remove(shaker_config_path)
        print(f"\n[*] Cleaned up temporary config {shaker_config_path}")
        
    print("=====================================================")
    print(" Shaker Data Collection Complete!")
    print(" Data saved to: rpi/experiments/results/shaker")
    print("=====================================================")

if __name__ == "__main__":
    main()
