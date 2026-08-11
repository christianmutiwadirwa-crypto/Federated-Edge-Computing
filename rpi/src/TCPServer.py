import socket
import threading
from PacketReceiver import PacketReceiver
from DataManager import DataManager
from Logger import Logger

class TCPServer:
    """Multithreaded TCP Server listening for ESP32 connections."""
    
    def __init__(self, config_manager, data_manager: DataManager, logger: Logger):
        self.port = config_manager.get("tcp_port", 9000)
        self.max_connections = config_manager.get("max_connections", 10)
        self.data_manager = data_manager
        self.logger = logger
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("0.0.0.0", self.port))
        
        self.running = False
        self.receivers = []
        self.thread = None

    def start(self):
        self.running = True
        self.server_socket.listen(self.max_connections)
        self.logger.log(f"Server startup: Listening on port {self.port}", severity="INFO")
        print(f"\n[SERVER] Listening for ESP32 connections on port {self.port} ...")
        
        self.thread = threading.Thread(target=self._accept_loop, name="TCPServerAcceptThread", daemon=True)
        self.thread.start()

    def _accept_loop(self):
        while self.running:
            try:
                # Use a timeout to allow checking self.running gracefully
                self.server_socket.settimeout(1.0)
                try:
                    conn, addr = self.server_socket.accept()
                    conn.settimeout(None) # Reset timeout for normal operation
                except socket.timeout:
                    continue
                
                # Create a new receiver thread for this connection
                receiver = PacketReceiver(
                    conn=conn, 
                    addr=addr, 
                    data_manager=self.data_manager, 
                    logger=self.logger,
                    server_ip="0.0.0.0",
                    server_port=self.port
                )
                self.receivers.append(receiver)
                
                # Cleanup dead receivers
                self.receivers = [r for r in self.receivers if r.thread.is_alive()]
                
            except Exception as e:
                if self.running:
                    self.logger.log(f"TCPServer accept error: {e}", severity="ERROR")

    def stop(self):
        self.logger.log("Server shutdown initiated.", severity="INFO")
        self.running = False
        if self.thread:
            self.thread.join()
        for receiver in self.receivers:
            receiver.stop()
        self.server_socket.close()
        self.logger.log("Server shutdown complete.", severity="INFO")
