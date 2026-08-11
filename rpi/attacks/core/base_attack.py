from abc import ABC, abstractmethod

from core.logger import Logger
from core.config_manager import ConfigManager
from core.network_manager import NetworkManager
from core.packet_capture import PacketCapture
from core.packet_sender import PacketSender

class Attack(ABC):
    """
    Abstract base class for all cyber attack plugins.
    Ensures a common interface and provides access to core framework components.
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

    @abstractmethod
    def execute(self) -> None:
        """
        The main execution method for the attack.
        Must be overridden by all subclasses.
        """
        pass
