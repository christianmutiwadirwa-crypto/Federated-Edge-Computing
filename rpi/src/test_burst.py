import sys, time, queue
sys.path.insert(0, 'd:/Projects/Federated Learning/rpi/src')

print('Checking CyberFeatureExtractor Burst Intensity Logic')

class MockCfg:
    def get(self, k, d=None):
        return {'window_duration_sec': 2}.get(k, d)

from CyberFeatureExtractor import CyberFeatureExtractor
from SlidingWindow import PacketEntry

ext = CyberFeatureExtractor(MockCfg())

# 10 packets at exactly 0.2s intervals (perfectly uniform over 2s)
packets = [
    PacketEntry(1000.0 + i*0.2, 1, 'a', 'b', 1, 2, 126, i,
                0.2 if i > 0 else 0.0, 0, False, False, True, True, 1000.0)
    for i in range(10)
]
f = ext.extract(0, 1000.0, 1002.0, packets, 0, 'Normal')
print(f'10 packets at 200ms intervals (10 of 20 bins filled): burst_intensity = {f["burst_intensity"]}')

# True uniform: 20 packets at 100ms intervals -> every bin gets exactly 1 packet
uniform = [
    PacketEntry(1000.0 + i*0.1, 1, 'a', 'b', 1, 2, 126, i,
                0.1 if i > 0 else 0.0, 0, False, False, True, True, 1000.0)
    for i in range(20)
]
f2 = ext.extract(0, 1000.0, 1002.0, uniform, 0, 'Normal')
print(f'20 packets at 100ms intervals (all bins filled): burst_intensity = {f2["burst_intensity"]}')

# Burst: 20 packets all in first 10ms
burst = [
    PacketEntry(1000.0 + i*0.001, 1, 'a', 'b', 1, 2, 126, i,
                0.001 if i > 0 else 0.0, 0, False, False, True, True, 1000.0)
    for i in range(20)
]
f3 = ext.extract(0, 1000.0, 1002.0, burst, 0, 'Normal')
print(f'20 packets all in first 10ms (single-bin flood): burst_intensity = {f3["burst_intensity"]}')
