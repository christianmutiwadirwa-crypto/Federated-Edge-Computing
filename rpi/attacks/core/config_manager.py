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
        """Loads the JSON configuration file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path.absolute()}")
        
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
