#!/usr/bin/env python3
import json
import os
import subprocess
import time

def main():
    config_path = "config/config.json"
    eval_config_path = "config/eval_config.json"
    
    pre_duration = 30.0
    post_duration = 30.0
    attack_duration = 600.0 # 10 minutes per attack
    
    print("=====================================================")
    print(" Starting Evaluation Data Collection Scheduler")
    print(f" Output Directory: results/evaluation")
    print("=====================================================")
    
    # 1. Read existing config
    if not os.path.exists(config_path):
        print(f"[!] Error: Cannot find {config_path}")
        return
        
    with open(config_path, "r") as f:
        config_data = json.load(f)
        
    # 2. Modify config for evaluation
    config_data["results_dir"] = "results/evaluation"
    
    experiments = config_data.get("experiments", {})
    if not experiments:
        print("[!] Error: No experiments found in config.")
        return
        
    num_experiments = len(experiments)
    total_time_per_exp = pre_duration + attack_duration + post_duration
    total_duration_mins = (num_experiments * total_time_per_exp) / 60.0
    
    print(f"[*] Found {num_experiments} experiments. Setting attack duration to {attack_duration:.1f}s each.")
    print(f"[*] Total estimated runtime: ~{total_duration_mins:.1f} minutes.")
        
    for exp_key in experiments:
        experiments[exp_key]["pre_attack_duration"] = pre_duration
        experiments[exp_key]["attack_duration"] = attack_duration
        experiments[exp_key]["post_attack_duration"] = post_duration
        
    # 3. Write temp eval config
    with open(eval_config_path, "w") as f:
        json.dump(config_data, f, indent=4)
        
    print(f"[*] Generated temporary config at {eval_config_path}")
    print("[*] Starting experiments...")
    
    # Only run the 9 active classes for the final federation
    active_classes = {
        "NormalExperiment",
        "FloodingExperiment",
        "SlowDoSExperiment",
        "PacketInjectionMalformedExperiment",
        "PacketLossExperiment",
        "DuplicatePacketExperiment",
        "DeviceSpoofHardExperiment",
        "DataTamperingBitFlipExperiment",
        "DataTamperingCRCForgedExperiment"
    }
    
    # 4. Run all active experiments
    exp_keys = [k for k in experiments.keys() if k in active_classes]
    
    for i, exp_key in enumerate(exp_keys, 1):
        # We need the base experiment name without 'Experiment' suffix 
        # (e.g. 'ReplayExperiment' -> 'Replay' as expected by main.py arg)
        exp_name = exp_key.replace("Experiment", "")
        
        print(f"\n[{i}/{len(exp_keys)}] Running {exp_name}...")
        try:
            # We use python main.py --experiment XXX --config config/eval_config.json
            # Add a 5-minute safety buffer timeout to prevent hanging.
            subprocess.run(
                ["python", "main.py", "--experiment", exp_name, "--config", eval_config_path],
                check=True,
                timeout=total_time_per_exp + 300
            )
        except subprocess.CalledProcessError:
            print(f"[!] Error: Experiment {exp_name} failed. Continuing to next...")
        except subprocess.TimeoutExpired:
            print(f"[!] Critical: Experiment {exp_name} hung and timed out. Force killed. Continuing...")
        except KeyboardInterrupt:
            print("\n[!] Collection aborted by user.")
            break
            
    # 5. Cleanup
    if os.path.exists(eval_config_path):
        os.remove(eval_config_path)
        print(f"\n[*] Cleaned up temporary config {eval_config_path}")
        
    print("=====================================================")
    print(" Evaluation Data Collection Complete!")
    print(" Data saved to: rpi/experiments/results/evaluation")
    print("=====================================================")

if __name__ == "__main__":
    main()
