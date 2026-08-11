import os
from pathlib import Path
import logging

class LabelManager:
    """
    Manages the IPC (Inter-Process Communication) with the Edge Node
    by writing the current experiment's attack label to the shared state file.
    """

    def __init__(self, config: dict, logger: logging.Logger):
        """
        Initializes the LabelManager.
        
        Args:
            config: Framework configuration dictionary.
            logger: Framework logger instance.
        """
        self.logger = logger
        # Default path relative to the experiments directory, assuming EdgeNode is in ../src/EdgeNode
        default_state_dir = str(Path(__file__).resolve().parent.parent.parent / "src" / "EdgeNode" / "state")
        
        state_dir_path = config.get("edge_node_state_dir", default_state_dir)
        self.state_file = Path(state_dir_path) / "attack_label.txt"
        
        # Ensure the directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def set_label(self, label: str) -> None:
        """
        Writes the given label to the state file so the EdgeNode WindowManager can read it.
        """
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                f.write(label)
            self.logger.info(f"IPC Label successfully set to: '{label}'")
        except Exception as e:
            self.logger.error(f"Failed to write IPC label '{label}' to {self.state_file}: {e}")

    def reset(self) -> None:
        """
        Resets the label back to the baseline 'Normal' state.
        """
        self.set_label("Normal")
