import os
import re

d = 'd:/Projects/Federated Learning/rpi/experiments/experiments'
for f in os.listdir(d):
    if not f.endswith('.py'): continue
    path = os.path.join(d, f)
    with open(path, 'r') as file:
        content = file.read()
    
    # Check if already modified
    if "_start_attack" in content:
        continue
        
    # 1. Inject _start_attack() after time.sleep(pre_attack)
    content = re.sub(r'(time\.sleep\(pre_attack\)\s*)', r'\1\n        self._start_attack()\n\n', content)
    
    # 2. Inject _stop_attack() before the post_attack section starts
    content = re.sub(r'(\s+post_attack = self\.experiment_config\.get\("post_attack_duration")', r'\n        self._stop_attack()\n\1', content)
    
    # Write back
    with open(path, 'w') as file:
        file.write(content)
print('Done.')
