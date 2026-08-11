import sys
from typing import Optional

# We try to import scapy, but handle the case where it's not installed gracefully
# so the framework can throw a clear error message.
try:
    from scapy.all import conf, get_if_list
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False


from core.config_manager import ConfigManager
from core.logger import Logger

class NetworkManager:
    """
    Manages network interface configuration and validation for Scapy.
    Abstracts Scapy interface details from the rest of the framework.
    """
    
    def __init__(self, config_manager: ConfigManager, logger: Logger):
        self.config_manager = config_manager
        self.logger = logger
        self.interface = self.config_manager.get("network_interface", "eth0")
        
        self._validate_environment()

    def _validate_environment(self) -> None:
        if not SCAPY_AVAILABLE:
            self.logger.error("Scapy is not installed. Please install it using: pip install scapy")
            sys.exit(1)
            
        # Verify the interface exists (this is more reliable on Linux/Mac than Windows,
        # but we do a best-effort check).
        available_interfaces = get_if_list()
        
        # Scapy on Windows sometimes formats interface names weirdly (e.g., UUIDs or descriptions).
        # We'll log a warning if it doesn't match exactly, rather than crashing, 
        # to ensure it's still usable on Windows for development if needed.
        if self.interface not in available_interfaces:
            self.logger.warning(
                f"Interface '{self.interface}' not found in Scapy's interface list: {available_interfaces}. "
                f"Packet capture/injection may fail if the name is incorrect."
            )
        else:
            self.logger.debug(f"Network interface '{self.interface}' validated.")
            
        # Set the default Scapy interface to avoid having to pass it to every function
        conf.iface = self.interface

    def get_interface(self) -> str:
        """Returns the configured network interface name."""
        return self.interface
