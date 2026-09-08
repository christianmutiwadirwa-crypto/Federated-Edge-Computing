#!/usr/bin/env python3
import json
import os
import subprocess
import time

def main():
    config_path = "config/config.json"
    eval_config_path = "config/eval_config.json"
    
    # 90 minutes = 5400 seconds
    # 11 experiments total
    # Total time per experiment = 5400 / 11 = ~491 seconds
    pre_duration = 30.0
    post_duration = 30.0
    attack_duration = 431.0 # 491 - 30 - 30 = 431
    
    print("=====================================================")
    print(" Starting Evaluation Data Collection Scheduler")
    print(f" Total Duration: 90 Minutes")
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
        
    for exp_key in experiments:
        experiments[exp_key]["pre_attack_duration"] = pre_duration
        experiments[exp_key]["attack_duration"] = attack_duration
        experiments[exp_key]["post_attack_duration"] = post_duration
        
    # 3. Write temp eval config
    with open(eval_config_path, "w") as f:
        json.dump(config_data, f, indent=4)
        
    print(f"[*] Generated temporary config at {eval_config_path}")
    print("[*] Starting experiments...")
    
    # 4. Run all experiments
    exp_keys = list(experiments.keys())
    for i, exp_key in enumerate(exp_keys, 1):
        # We need the base experiment name without 'Experiment' suffix 
        # (e.g. 'ReplayExperiment' -> 'Replay' as expected by main.py arg)
        exp_name = exp_key.replace("Experiment", "")
        
        print(f"\n[{i}/{len(exp_keys)}] Running {exp_name}...")
        try:
            # We use python main.py --experiment XXX --config config/eval_config.json
            subprocess.run(
                ["python", "main.py", "--experiment", exp_name, "--config", eval_config_path],
                check=True
            )
        except subprocess.CalledProcessError:
            print(f"[!] Error: Experiment {exp_name} failed. Continuing to next...")
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
