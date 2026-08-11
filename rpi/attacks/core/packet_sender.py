import time
from typing import List

try:
    from scapy.all import sendp, send, Packet, Ether
except ImportError:
    pass # Handled by NetworkManager

from core.logger import Logger
from core.network_manager import NetworkManager

class PacketSender:
    """
    Responsible only for transmitting packets onto the network interface.
    """
    
    def __init__(self, network_manager: NetworkManager, logger: Logger):
        self.network_manager = network_manager
        self.logger = logger

    def replay_packets(self, packets: List['Packet'], count: int = 1, interval_ms: int = 500) -> None:
        """
        Replays a list of packets exactly as they were captured.
        
        Args:
            packets (List[Packet]): The packets to replay.
            count (int): How many times to loop through the packet list.
            interval_ms (int): Delay between each packet transmission in milliseconds.
        """
        if not packets:
            self.logger.warning("No packets provided to replay.")
            return

        interface = self.network_manager.get_interface()
        interval_sec = interval_ms / 1000.0

        for iteration in range(count):
            for i, pkt in enumerate(packets):
                # We attempt to send at Layer 2 (Ethernet) to guarantee bit-for-bit accuracy.
                # Scapy's sendp() requires an Ethernet layer frame.
                if pkt.haslayer(Ether):
                    try:
                        # sendp is for Layer 2. verbose=False prevents scapy from printing to stdout directly.
                        sendp(pkt, iface=interface, verbose=False)
                        self.logger.info(f"Replaying Packet #{i+1}")
                    except Exception as e:
                        self.logger.error(f"Failed to send packet #{i+1} at Layer 2: {e}")
                else:
                    # Fallback to Layer 3 (IP) if the captured packet doesn't have an Ethernet frame.
                    try:
                        send(pkt, iface=interface, verbose=False)
                        self.logger.info(f"Replaying Packet #{i+1} (Layer 3 fallback)")
                    except Exception as e:
                        self.logger.error(f"Failed to send packet #{i+1} at Layer 3: {e}")
                
                # Apply the replay interval (skip delay after the very last packet)
                if not (iteration == count - 1 and i == len(packets) - 1):
                    time.sleep(interval_sec)
