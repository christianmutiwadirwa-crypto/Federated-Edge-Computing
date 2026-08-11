import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from ConfigManager import ConfigManager

class Logger:
    """Thread-safe event logger."""
    
    def __init__(self, config_manager: ConfigManager, log_queue: queue.Queue):
        self.log_queue = log_queue
        self.running = True
        
        base_dir = Path(config_manager.get("directories", {}).get("base", "EdgeNode"))
        logs_dir = base_dir / config_manager.get("directories", {}).get("logs", "logs")
        self.log_file_path = logs_dir / "events.log"
        
        self.thread = threading.Thread(target=self._log_worker, name="LoggerThread", daemon=True)
        self.thread.start()

    def _log_worker(self):
        """Worker thread that processes the log queue."""
        with open(self.log_file_path, "a") as f:
            while self.running or not self.log_queue.empty():
                try:
                    # Block with timeout to allow checking self.running
                    msg_dict = self.log_queue.get(timeout=0.1)
                    
                    timestamp = msg_dict.get('timestamp', datetime.utcnow().isoformat())
                    severity = msg_dict.get('severity', 'INFO')
                    node_id = msg_dict.get('node_id', 'N/A')
                    message = msg_dict.get('message', '')
                    
                    log_line = f"{timestamp} [{severity}] Node: {node_id} - {message}\n"
                    f.write(log_line)
                    f.flush()
                    self.log_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"Logger Error: {e}")

    def log(self, message: str, severity: str = "INFO", node_id: str = "N/A"):
        """Queue a message to be logged."""
        msg_dict = {
            'timestamp': datetime.utcnow().isoformat(),
            'severity': severity,
            'node_id': node_id,
            'message': message
        }
        try:
            self.log_queue.put_nowait(msg_dict)
        except queue.Full:
            print(f"Log queue full. Dropped message: {message}")

    def stop(self):
        """Stop the logging thread gracefully."""
        self.running = False
        self.thread.join()
