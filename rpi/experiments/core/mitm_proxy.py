import socket
import threading
import time
import logging

class MITMProxy:
    """
    Transparent TCP proxy that intercepts connections between the ESP32 and the IDS server.
    Provides hooks for manipulating timing, dropping packets, and tampering with data.
    """
    def __init__(self, listen_port: int, target_ip: str, target_port: int, logger: logging.Logger):
        self.listen_port = listen_port
        self.target_ip = target_ip
        self.target_port = target_port
        self.logger = logger
        self.server_socket = None
        self.client_socket = None
        self.target_socket = None
        self.running = False

    def start(self):
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("0.0.0.0", self.listen_port))
        self.server_socket.listen(1)
        
        self.logger.info(f"[MITM Proxy] Listening on port {self.listen_port}, forwarding to {self.target_ip}:{self.target_port}")
        
        # Accept one connection (the ESP32)
        try:
            self.server_socket.settimeout(30.0) # Wait 30s for ESP32 to connect
            self.client_socket, addr = self.server_socket.accept()
            self.logger.info(f"[MITM Proxy] Intercepted connection from ESP32 at {addr}")
            
            # Connect to actual server
            self.target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.target_socket.connect((self.target_ip, self.target_port))
            self.logger.info(f"[MITM Proxy] Connected to real server at {self.target_ip}:{self.target_port}")
            
            # Start forwarding threads
            t1 = threading.Thread(target=self._forward_client_to_server, daemon=True)
            t2 = threading.Thread(target=self._forward_server_to_client, daemon=True)
            t1.start()
            t2.start()
        except Exception as e:
            self.logger.error(f"[MITM Proxy] Failed to establish proxy: {e}")
            self.stop()

    def stop(self):
        self.running = False
        for sock in [self.client_socket, self.target_socket, self.server_socket]:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def _forward_client_to_server(self):
        """Intercepts data from ESP32, applies attack manipulation, forwards to server."""
        while self.running:
            try:
                data = self.client_socket.recv(4096)
                if not data:
                    break
                
                # Apply attack logic
                manipulated_data = self.process_esp32_data(data)
                
                if manipulated_data:
                    self.target_socket.sendall(manipulated_data)
            except Exception as e:
                if self.running:
                    self.logger.error(f"[MITM Proxy] Client->Server error: {e}")
                break
        self.stop()

    def _forward_server_to_client(self):
        """Forward server responses back to ESP32 without modification."""
        while self.running:
            try:
                data = self.target_socket.recv(4096)
                if not data:
                    break
                self.client_socket.sendall(data)
            except Exception:
                break
        self.stop()

    def process_esp32_data(self, data: bytes) -> bytes:
        """
        Override this method in subclasses to drop, delay, or tamper with data.
        Return None to drop the packet.
        """
        return data
