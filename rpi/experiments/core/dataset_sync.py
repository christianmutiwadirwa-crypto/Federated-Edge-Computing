import os
import shutil
import time
from pathlib import Path
import logging

class DatasetSynchronizer:
    """
    Handles the secure archival and synchronization of generated dataset CSVs 
    from the Edge Node after an experiment finishes.
    """

    def __init__(self, config: dict, logger: logging.Logger):
        self.logger = logger
        
        # Determine the source directories where Edge Node writes CSVs
        default_edge_dir = Path(__file__).resolve().parent.parent.parent / "src" / "EdgeNode"
        self.cyber_csv = Path(config.get("edge_node_cyber_csv", default_edge_dir / "cyber" / "cyber_data.csv"))
        self.physical_csv = Path(config.get("edge_node_physical_csv", default_edge_dir / "physical" / "physical_data.csv"))
        
        # Determine local results directory
        self.results_dir = Path(config.get("results_dir", "results"))
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        self.cyber_start_line = 0
        self.physical_start_line = 0

    def mark_start(self) -> None:
        """
        Records the current line count of the Edge Node CSVs right before 
        an experiment begins. This allows us to extract only the new rows 
        generated during the experiment.
        """
        self.cyber_start_line = self._count_lines(self.cyber_csv)
        self.physical_start_line = self._count_lines(self.physical_csv)
        self.logger.debug(f"Marked start lines: cyber={self.cyber_start_line}, physical={self.physical_start_line}")

    def _count_lines(self, path: Path) -> int:
        if not path.exists():
            return 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def sync_datasets(self, experiment_name: str) -> None:
        """
        Copies the cyber and physical CSV files into a timestamped archival directory
        under the local results/ folder.
        """
        timestamp = int(time.time())
        archive_name = f"{experiment_name}_{timestamp}"
        archive_path = self.results_dir / archive_name
        
        try:
            archive_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Syncing datasets to archive: {archive_path}")
            
            synced_count = 0
            
            if self.cyber_csv.exists():
                dest = archive_path / "cyber_data.csv"
                self._extract_experiment_data(self.cyber_csv, dest, self.cyber_start_line)
                self.logger.info(f" -> Synced and isolated cyber_data.csv")
                synced_count += 1
            else:
                self.logger.warning(f" -> Source cyber_data.csv not found at {self.cyber_csv}")
                
            if self.physical_csv.exists():
                dest = archive_path / "physical_data.csv"
                self._extract_experiment_data(self.physical_csv, dest, self.physical_start_line)
                self.logger.info(f" -> Synced and isolated physical_data.csv")
                synced_count += 1
            else:
                self.logger.warning(f" -> Source physical_data.csv not found at {self.physical_csv}")
                
            if synced_count == 0:
                self.logger.warning("Dataset synchronization finished with 0 files copied.")
            else:
                self.logger.info(f"Dataset synchronization complete. {synced_count} files archived.")
                
        except Exception as e:
            self.logger.error(f"Failed to synchronize datasets for {experiment_name}: {e}")

    def _extract_experiment_data(self, source_path: Path, dest_path: Path, start_line: int) -> None:
        """
        Reads the source CSV, copies the header (line 0), skips rows up to `start_line`,
        and writes the remaining rows to `dest_path`.
        """
        try:
            with open(source_path, "r", encoding="utf-8") as src, \
                 open(dest_path, "w", encoding="utf-8", newline="") as dst:
                
                # Copy the header
                header = src.readline()
                if header:
                    dst.write(header)
                
                # Skip previously existing rows (minus the header we already read)
                lines_to_skip = max(0, start_line - 1)
                for _ in range(lines_to_skip):
                    src.readline()
                    
                # Write only the new rows generated during the experiment
                for line in src:
                    dst.write(line)
        except Exception as e:
            self.logger.error(f"Error extracting experiment data from {source_path}: {e}")
