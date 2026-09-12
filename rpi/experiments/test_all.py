import sys
import subprocess
import json
import os

experiments = [
    'Replay', 'Flooding', 'SlowDoS', 'PacketInjectionMalformed', 'PacketInjectionConformant',
    'PacketLoss', 'DuplicatePacket', 'Delay', 'ConnectionReset', 'ReconScan',
    'DeviceSpoofHard', 'DataTamperingBitFlip', 'DataTamperingCRCForged', 'Normal'
]

def create_temp_config():
    with open('config/config.json', 'r') as f:
        config = json.load(f)
    
    config['results_dir'] = 'results'
    for exp_key in config.get('experiments', {}):
        config['experiments'][exp_key]['pre_attack_duration'] = 1.0
        config['experiments'][exp_key]['attack_duration'] = 5.0
        config['experiments'][exp_key]['post_attack_duration'] = 1.0
        
    with open('config/test_config.json', 'w') as f:
        json.dump(config, f, indent=4)

print('Full framework lifecycle test for all 14 experiments')
print('=' * 55)

create_temp_config()
failures = []

for exp in experiments:
    try:
        result = subprocess.run(
            ['python', 'main.py', '--experiment', exp, '--config', 'config/test_config.json'],
            capture_output=True, text=True, timeout=20
        )
        lines = result.stdout.splitlines()
        completed  = any('completed' in l.lower() for l in lines)
        cleanup    = any('cleaned up' in l.lower() for l in lines)
        sync       = any('sync' in l.lower() for l in lines)
        if result.returncode == 0 and completed and cleanup and sync:
            print(f'  OK  {exp:35s}')
        else:
            failures.append(exp)
            print(f'  FAIL {exp}')
            if result.stderr:
                print(result.stderr[:300])
    except subprocess.TimeoutExpired:
        failures.append(exp)
        print(f'  TIMEOUT {exp}')

if os.path.exists('config/test_config.json'):
    os.remove('config/test_config.json')

print()
print(f'RESULT: {len(experiments)-len(failures)}/{len(experiments)} passed')
sys.exit(0 if not failures else 1)
