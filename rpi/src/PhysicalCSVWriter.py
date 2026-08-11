import csv
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

class PhysicalCSVWriter:
    """Thread-safe writer for physical data to CSV."""
    
    HEADERS = [
        "Timestamp", "Node ID", 
        "Mean X", "Mean Y", "Mean Z",
        "RMS X", "RMS Y", "RMS Z",
        "Standard Deviation X", "Standard Deviation Y", "Standard Deviation Z",
        "Maximum X", "Maximum Y", "Maximum Z",
        "Minimum X", "Minimum Y", "Minimum Z",
        "Peak-to-Peak X", "Peak-to-Peak Y", "Peak-to-Peak Z",
        "Skewness X", "Skewness Y", "Skewness Z",
        "Kurtosis X", "Kurtosis Y", "Kurtosis Z",
        "Crest Factor X", "Crest Factor Y", "Crest Factor Z",
        "Label"
    ]

    def __init__(self, config_manager, data_queue: queue.Queue):
        self.data_queue = data_queue
        self.running = True
        self.flush_interval = config_manager.get("csv_flush_interval_sec", 5)
        
        base_dir = Path(config_manager.get("directories", {}).get("base", "EdgeNode"))
        physical_dir = base_dir / config_manager.get("directories", {}).get("physical", "physical")
        self.file_path = physical_dir / "physical_data.csv"
        
        self._ensure_header()
        
        self.thread = threading.Thread(target=self._writer_worker, name="PhysicalWriterThread", daemon=True)
        self.thread.start()

    def _ensure_header(self):
        """Creates file and header if it doesn't exist."""
        write_header = not self.file_path.exists() or self.file_path.stat().st_size == 0
        if write_header:
            with open(self.file_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)

    def _writer_worker(self):
        last_flush = time.time()
        
        with open(self.file_path, "a", newline="") as f:
            writer = csv.writer(f)
            while self.running or not self.data_queue.empty():
                try:
                    data = self.data_queue.get(timeout=1.0)
                    row = self._format_row(data)
                    writer.writerow(row)
                    self.data_queue.task_done()
                    
                    if time.time() - last_flush > self.flush_interval:
                        f.flush()
                        last_flush = time.time()
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"PhysicalCSVWriter Error: {e}")

    def _format_row(self, data: dict) -> list:
        features = data.get("features", {})
        arrival_time = data.get("arrival_time")
        if arrival_time:
            timestamp = datetime.fromtimestamp(arrival_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            timestamp = data.get("timestamp_ms", 0)  # Fallback to millis if not available
        return [
            timestamp,
            data.get("node_id", -1),
            features.get("mean_x", 0), features.get("mean_y", 0), features.get("mean_z", 0),
            features.get("rms_x", 0), features.get("rms_y", 0), features.get("rms_z", 0),
            features.get("std_x", 0), features.get("std_y", 0), features.get("std_z", 0),
            features.get("max_x", 0), features.get("max_y", 0), features.get("max_z", 0),
            features.get("min_x", 0), features.get("min_y", 0), features.get("min_z", 0),
            features.get("p2p_x", 0), features.get("p2p_y", 0), features.get("p2p_z", 0),
            features.get("skew_x", 0), features.get("skew_y", 0), features.get("skew_z", 0),
            features.get("kurt_x", 0), features.get("kurt_y", 0), features.get("kurt_z", 0),
            features.get("crf_x", 0), features.get("crf_y", 0), features.get("crf_z", 0),
            "Normal" # Default Label
        ]

    def stop(self):
        self.running = False
        self.thread.join()
