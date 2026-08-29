#!/usr/bin/env python3
"""
=============================================================================
 Raspberry Pi Edge Node - Predictive Maintenance System
=============================================================================
 Entry point for the Raspberry Pi TCP receiver and feature extraction node.
 Receives physical data packets from ESP32 nodes, validates them, extracts
 cyber features, and logs them to datasets for future ML analysis.
 
 Designed for 24/7 continuous operation.
=============================================================================
"""

import time
import queue
import signal
import sys
from ConfigManager import ConfigManager
from Logger import Logger
from DataManager import DataManager
from TCPServer import TCPServer
from WebDashboard import WebDashboard

class EdgeNodeApp:
    def __init__(self):
        self.config_manager = ConfigManager()
        
        # Thread 6: Logger (initialized first so others can use it)
        log_queue_size = self.config_manager.get("queue_sizes", {}).get("log_queue", 1000)
        self.log_queue = queue.Queue(maxsize=log_queue_size)
        self.logger = Logger(self.config_manager, self.log_queue)
        
        # Threads 2, 3, 4, 5 managed by DataManager
        self.data_manager = DataManager(self.config_manager, self.logger)
        
        # Thread 1: TCP Server (which spawns PacketReceiver threads)
        self.tcp_server = TCPServer(self.config_manager, self.data_manager, self.logger)
        
        # Thread 7: Web Dashboard (FastAPI)
        self.web_dashboard = WebDashboard(self.config_manager, self.data_manager, self.logger)
        
        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self.graceful_shutdown)
        signal.signal(signal.SIGTERM, self.graceful_shutdown)

    def start(self):
        self.tcp_server.start()
        self.web_dashboard.start()
        
        try:
            # Main thread just sleeps and keeps the process alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.graceful_shutdown(None, None)

    def graceful_shutdown(self, signum, frame):
        print("\nInitiating graceful shutdown...")
        self.tcp_server.stop()
        self.data_manager.stop()
        self.logger.stop()
        print("Shutdown complete.")
        sys.exit(0)

if __name__ == "__main__":
    app = EdgeNodeApp()
    app.start()
