import importlib
import sys

from core.logger import Logger
from core.config_manager import ConfigManager
from core.network_manager import NetworkManager
from core.packet_capture import PacketCapture
from core.packet_sender import PacketSender
from core.base_attack import Attack

class AttackController:
    """
    Central manager that dynamically loads and executes the selected attack module.
    """
    
    def __init__(self, 
                 config_manager: ConfigManager, 
                 logger: Logger, 
                 network_manager: NetworkManager, 
                 packet_capture: PacketCapture, 
                 packet_sender: PacketSender):
        self.config_manager = config_manager
        self.logger = logger
        self.network_manager = network_manager
        self.packet_capture = packet_capture
        self.packet_sender = packet_sender

    def _load_attack_module(self, attack_name: str) -> Attack:
        """
        Dynamically imports the attack class from the 'attacks' directory based on the config name.
        Assumes the file is named lowercase (e.g. 'replay.py') and the class is named camelcase (e.g. 'ReplayAttack').
        """
        module_name = f"attacks.{attack_name.lower()}"
        class_name = f"{attack_name}Attack"
        
        try:
            self.logger.debug(f"Attempting to load {class_name} from {module_name}")
            module = importlib.import_module(module_name)
            attack_class = getattr(module, class_name)
            
            # Instantiate the attack plugin with dependencies injected
            return attack_class(
                config_manager=self.config_manager,
                logger=self.logger,
                network_manager=self.network_manager,
                packet_capture=self.packet_capture,
                packet_sender=self.packet_sender
            )
        except ModuleNotFoundError:
            self.logger.error(f"Attack module '{module_name}' not found. Ensure the file exists in the attacks/ directory.")
            sys.exit(1)
        except AttributeError:
            self.logger.error(f"Class '{class_name}' not found inside module '{module_name}'.")
            sys.exit(1)
        except Exception as e:
            self.logger.error(f"Failed to load attack module '{attack_name}': {e}")
            sys.exit(1)

    def execute(self) -> None:
        """Loads and runs the configured attack."""
        attack_name = self.config_manager.get("attack", "Replay")
        self.logger.info(f"Initializing {attack_name} Attack module...")
        
        attack_instance = self._load_attack_module(attack_name)
        attack_instance.execute()
