from pathlib import Path
from typing import List, Optional

try:
    from scapy.all import sniff, wrpcap, Packet
except ImportError:
    pass # Handled by NetworkManager

from core.logger import Logger
from core.network_manager import NetworkManager

class PacketCapture:
    """
    Responsible only for capturing packets from the network interface.
    """
    
    def __init__(self, network_manager: NetworkManager, logger: Logger, bpf_filter: str):
        self.network_manager = network_manager
        self.logger = logger
        self.bpf_filter = bpf_filter
        
        # In-memory storage for captured packets
        self.captured_packets: List['Packet'] = []

    def capture(self, count: int, timeout: Optional[int] = None) -> List['Packet']:
        """
        Captures a specified number of packets matching the BPF filter.
        
        Args:
            count (int): The number of packets to capture.
            timeout (int, optional): Maximum time to wait for packets in seconds.
            
        Returns:
            List[Packet]: The list of captured Scapy packet objects.
        """
        interface = self.network_manager.get_interface()
        self.logger.info(f"Starting capture of {count} packets on {interface} with filter '{self.bpf_filter}'...")
        
        try:
            self.captured_packets = sniff(
                iface=interface,
                filter=self.bpf_filter,
                count=count,
                timeout=timeout
            )
            
            self.logger.info(f"Captured {len(self.captured_packets)} packets.")
            
            for i, pkt in enumerate(self.captured_packets):
                self.logger.info(f"Captured Packet #{i+1}")
                
            return self.captured_packets
            
        except Exception as e:
            self.logger.error(f"Failed to capture packets: {e}")
            return []

    def save_pcap(self, filename: str = "capture.pcap") -> bool:
        """
        Saves the currently captured packets to a PCAP file.
        
        Args:
            filename (str): The name of the file to save (will be placed in captures/ directory).
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if not self.captured_packets:
            self.logger.warning("No packets in memory to save.")
            return False
            
        save_path = Path("captures/replay_packets") / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            wrpcap(str(save_path), self.captured_packets)
            self.logger.debug(f"Saved {len(self.captured_packets)} packets to {save_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save PCAP to {save_path}: {e}")
            return False
