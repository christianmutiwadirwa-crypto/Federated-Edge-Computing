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
                shutil.copy2(self.cyber_csv, archive_path / "cyber_data.csv")
                self.logger.info(f" -> Synced cyber_data.csv")
                synced_count += 1
            else:
                self.logger.warning(f" -> Source cyber_data.csv not found at {self.cyber_csv}")
                
            if self.physical_csv.exists():
                shutil.copy2(self.physical_csv, archive_path / "physical_data.csv")
                self.logger.info(f" -> Synced physical_data.csv")
                synced_count += 1
            else:
                self.logger.warning(f" -> Source physical_data.csv not found at {self.physical_csv}")
                
            if synced_count == 0:
                self.logger.warning("Dataset synchronization finished with 0 files copied.")
            else:
                self.logger.info(f"Dataset synchronization complete. {synced_count} files archived.")
                
        except Exception as e:
            self.logger.error(f"Failed to synchronize datasets for {experiment_name}: {e}")
