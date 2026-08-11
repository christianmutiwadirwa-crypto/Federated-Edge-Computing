import socket
import threading
import time
from PacketParser import PacketParser
from DataManager import DataManager
from Logger import Logger

class PacketReceiver:
    """Handles an individual TCP connection and receives packets."""
    
    def __init__(self, conn: socket.socket, addr: tuple, data_manager: DataManager, logger: Logger, server_ip: str, server_port: int):
        self.conn = conn
        self.addr = addr
        self.data_manager = data_manager
        self.logger = logger
        self.running = True
        self.server_ip = server_ip
        self.server_port = server_port
        
        self.thread = threading.Thread(target=self._receive_loop, name=f"Receiver-{addr[0]}:{addr[1]}", daemon=True)
        self.thread.start()

    def _receive_loop(self):
        self.logger.log(f"Node connected: {self.addr}", severity="INFO")
        print(f"\n[+] SUCCESS: ESP32 Connected from {self.addr}")
        buf = bytearray()
        packet_size = PacketParser.PACKET_SIZE
        recv_count = 0
        
        try:
            while self.running:
                chunk = self.conn.recv(4096)
                if not chunk:
                    break # Connection closed
                
                recv_count += 1
                if recv_count % 50 == 1:
                    print(f"[*] Actively receiving data from {self.addr}... (Chunk #{recv_count})")
                
                arrival_time = time.time()
                buf.extend(chunk)
                
                while len(buf) >= packet_size:
                    raw_packet = bytes(buf[:packet_size])
                    del buf[:packet_size]
                    
                    # Offload to DataManager/Validation Queue immediately
                    # to ensure Reception Thread is never blocked
                    self.data_manager.process_raw_packet(
                        raw_packet,
                        src_ip=self.addr[0],
                        dst_ip=self.server_ip,
                        src_port=self.addr[1],
                        dst_port=self.server_port,
                        arrival_time=arrival_time
                    )
                    
                    try:
                        self.conn.sendall(b'\x06')
                    except Exception as e:
                        self.logger.log(f"Failed to send ACK to {self.addr}: {e}", severity="WARNING")
                    
        except ConnectionResetError:
            self.logger.log(f"Connection reset by node {self.addr}", severity="WARNING")
        except Exception as e:
            self.logger.log(f"Receiver error for {self.addr}: {e}", severity="ERROR")
        finally:
            self.conn.close()
            self.logger.log(f"Node disconnected: {self.addr}", severity="INFO")
            print(f"\n[-] ESP32 Disconnected: {self.addr}")

    def stop(self):
        self.running = False
        self.conn.close()
        self.thread.join()
