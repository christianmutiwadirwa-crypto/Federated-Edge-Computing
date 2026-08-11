import json
from pathlib import Path
from typing import Any, Dict

class ConfigManager:
    """
    Responsible for loading and providing access to the attack framework's configuration.
    """
    
    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> None:
        """Loads the JSON configuration file, or creates a default one if it doesn't exist."""
        if not self.config_path.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            default_config = {
                "experiment": "Replay",
                "schedule_delay_sec": 0,
                "results_dir": "results",
                "logging": {
                    "level": "INFO",
                    "file": "logs/experiment.log",
                    "format": "%(asctime)s [%(levelname)s] [%(module)s] %(message)s"
                }
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            self.config = default_config
            return
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a configuration value.
        
        Args:
            key (str): The configuration key to retrieve.
            default (Any): The value to return if the key is not found.
            
        Returns:
            Any: The configuration value.
        """
        return self.config.get(key, default)
