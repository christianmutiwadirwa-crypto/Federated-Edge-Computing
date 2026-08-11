import logging
import sys
from pathlib import Path
from typing import Optional

from core.config_manager import ConfigManager

class Logger:
    """
    Thread-safe logger responsible for logging framework events to both
    the console and a log file.
    """
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        
        log_config = self.config_manager.get("logging", {})
        self.log_level_str = log_config.get("level", "INFO").upper()
        self.log_file = log_config.get("file", "logs/framework.log")
        
        self.logger = logging.getLogger("AttackFramework")
        self.logger.setLevel(self._get_logging_level(self.log_level_str))
        
        # Prevent adding handlers multiple times if instantiated multiple times
        if not self.logger.handlers:
            self._setup_handlers()

    def _get_logging_level(self, level_str: str) -> int:
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        return levels.get(level_str, logging.INFO)

    def _setup_handlers(self) -> None:
        formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S')

        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File Handler
        try:
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(self.log_file, mode='a', encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to setup file logging at {self.log_file}: {e}")

    def info(self, message: str) -> None:
        self.logger.info(message)

    def error(self, message: str) -> None:
        self.logger.error(message)
        
    def warning(self, message: str) -> None:
        self.logger.warning(message)
        
    def debug(self, message: str) -> None:
        self.logger.debug(message)
