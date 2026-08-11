import sys, subprocess

experiments = [
    'Replay', 'Flooding', 'SlowDoS', 'PacketInjection', 'PacketLoss',
    'DuplicatePacket', 'Delay', 'ConnectionReset', 'DeviceSpoof', 'DataTampering'
]

print('Full framework lifecycle test for all experiments')
print('=' * 55)
failures = []
for exp in experiments:
    result = subprocess.run(
        ['python', 'main.py', '--experiment', exp],
        capture_output=True, text=True, timeout=15
    )
    lines = result.stdout.splitlines()
    label_line = [l for l in lines if 'Label' in l and 'set' in l]
    completed  = any('completed' in l.lower() for l in lines)
    cleanup    = any('cleaned up' in l.lower() for l in lines)
    sync       = any('Syncing datasets' in l for l in lines)
    if result.returncode == 0 and completed and cleanup and sync:
        label_val = label_line[0].split("'")[-2] if label_line and "'" in label_line[0] else '?'
        print(f'  OK  {exp:22s}  label={label_val}')
    else:
        failures.append(exp)
        print(f'  FAIL {exp}')
        if result.stderr:
            print(result.stderr[:300])

print()
print(f'RESULT: {len(experiments)-len(failures)}/{len(experiments)} passed')
sys.exit(0 if not failures else 1)
