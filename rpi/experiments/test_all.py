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
    completed  = any('completed' in l.lower() for l in lines)
    cleanup    = any('cleaned up' in l.lower() for l in lines)
    sync       = any('sync' in l.lower() for l in lines)
    if result.returncode == 0 and completed and cleanup and sync:
        print(f'  OK  {exp:22s}')
    else:
        failures.append(exp)
        print(f'  FAIL {exp}')
        if result.stderr:
            print(result.stderr[:300])

print()
print(f'RESULT: {len(experiments)-len(failures)}/{len(experiments)} passed')
sys.exit(0 if not failures else 1)
