import json
import os
from pathlib import Path

class ConfigManager:
    """Manages system configuration loaded from config.json."""
    
    def __init__(self, config_path: str = "EdgeNode/config/config.json"):
        self.config_path = Path(config_path)
        self.config = {}
        self._load_config()
        self._ensure_directories()

    def _load_config(self):
        if not self.config_path.exists():
            print(f"Configuration file not found. Creating default config at {self.config_path}")
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config = {
                "tcp_port": 9000,
                "max_connections": 10,
                "csv_flush_interval_sec": 5,
                # Duration of each cyber observation window (seconds).
                # Must match the ESP32's feature extraction interval for
                # physical/cyber dataset synchronisation.
                "window_duration_sec": 2,
                "queue_sizes": {
                    "log_queue": 1000,
                    "validation_queue": 1000,
                    "physical_writer_queue": 1000,
                    "cyber_writer_queue": 1000
                },
                "directories": {
                    "base": "EdgeNode",
                    "physical": "physical",
                    "cyber": "cyber",
                    "logs": "logs",
                    "state": "state"
                }
            }
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=4)
        else:
            with open(self.config_path, "r") as f:
                self.config = json.load(f)

    def _ensure_directories(self):
        """Creates required directories if they don't exist."""
        base_dir = Path(self.config.get("directories", {}).get("base", "EdgeNode"))
        dirs_cfg = self.config.get("directories", {})
        dirs_to_create = [
            base_dir / dirs_cfg.get("physical", "physical"),
            base_dir / dirs_cfg.get("cyber",    "cyber"),
            base_dir / dirs_cfg.get("logs",     "logs"),
            base_dir / dirs_cfg.get("state",    "state"),  # For attack_label.txt (IPC)
        ]
        for directory in dirs_to_create:
            directory.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, default=None):
        return self.config.get(key, default)
