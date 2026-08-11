# Cyber Attack Injection Framework

This framework generates reproducible cyber attacks against the Industrial IoT predictive maintenance testbed. It operates as an independent attacker on the network, passively observing legitimate traffic and injecting malicious packets without modifying the original ESP32 firmware or Raspberry Pi receiver software.

The framework captures cyber-features that can be used to generate labelled machine learning datasets.

## Requirements

The framework requires Python 3 and Scapy.

```bash
pip install scapy
```

*Note: On Linux systems (like the Raspberry Pi), packet capture and injection require root privileges. You must run the framework using `sudo`.*

## Configuration

Edit `config/config.json` to define the attack behavior.

```json
{
    "network_interface": "eth0",
    "bpf_filter": "tcp port 9000",
    "attack": "Replay",
    "capture_count": 5,
    "replay_count": 10,
    "delay_before_replay": 30,
    "replay_interval_ms": 500,
    "logging": {
        "level": "INFO",
        "file": "logs/framework.log"
    }
}
```

- **`network_interface`**: The interface to sniff/inject on (e.g., `eth0`, `wlan0`).
- **`bpf_filter`**: A standard tcpdump-style BPF filter to ensure the framework only captures packets destined for the target Raspberry Pi.
- **`attack`**: The name of the attack plugin to load (e.g., `"Replay"` loads `attacks/replay.py`).

## Running the Framework

```bash
cd rpi/attacks/
sudo python3 main.py
```

All output will be displayed on the console and appended to `logs/framework.log`. Any packets captured during an attack will be saved as a `.pcap` file in the `captures/replay_packets/` directory.

## Integrating Future Attacks

The framework is highly modular and designed using Object-Oriented principles. To add a new attack (e.g., `DelayAttack` or `FloodAttack`), you do not need to modify the core framework.

1. Create a new Python file in the `attacks/` directory, for example, `flood.py`.
2. Inside that file, create a class named `FloodAttack` that inherits from `core.base_attack.Attack`.
3. Implement the `execute(self)` method.

### Example: Creating a new attack

**File: `attacks/flood.py`**
```python
from core.base_attack import Attack

class FloodAttack(Attack):
    def execute(self) -> None:
        self.logger.info("Flood Attack Started")
        
        # You have access to all core utilities:
        # self.config_manager
        # self.packet_capture
        # self.packet_sender
        # self.network_manager
        
        # Implement custom attack logic here
        
        self.logger.info("Flood Attack Finished")
```

4. Update your `config.json` and set `"attack": "Flood"`. The framework's `AttackController` will automatically locate and load your new module at runtime.
