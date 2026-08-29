import importlib
import sys
import time

from core.logger import Logger
from core.config_manager import ConfigManager
from core.label_manager import LabelManager
from core.dataset_sync import DatasetSynchronizer
from core.base_experiment import BaseExperiment

class ExperimentManager:
    """
    Central orchestrator for the Cybersecurity Experiment Framework.
    Dynamically loads and safely executes the selected experiment,
    ensuring proper labeling and dataset synchronization.
    """
    
    def __init__(self, config_manager: ConfigManager, logger: Logger):
        self.config_manager = config_manager
        self.logger = logger
        self.label_manager = LabelManager(config_manager.config, logger)
        self.dataset_sync = DatasetSynchronizer(config_manager.config, logger)

    # Registry of all available experiment names → their module and class names.
    # Add new experiments here when a new experiment module is created.
    REGISTRY: dict = {
        "Replay":           ("experiments.replay_experiment",           "ReplayExperiment"),
        "Flooding":         ("experiments.flooding_experiment",         "FloodingExperiment"),
        "SlowDoS":          ("experiments.slowdos_experiment",          "SlowDoSExperiment"),
        "PacketInjection":  ("experiments.packetinjection_experiment",  "PacketInjectionExperiment"),
        "PacketLoss":       ("experiments.packetloss_experiment",       "PacketLossExperiment"),
        "DuplicatePacket":  ("experiments.duplicatepacket_experiment",  "DuplicatePacketExperiment"),
        "Delay":            ("experiments.delay_experiment",            "DelayExperiment"),
        "ConnectionReset":  ("experiments.connectionreset_experiment",  "ConnectionResetExperiment"),
        "DeviceSpoof":      ("experiments.devicespoof_experiment",      "DeviceSpoofExperiment"),
        "DataTampering":    ("experiments.datatampering_experiment",    "DataTamperingExperiment"),
        "Normal":           ("experiments.normal_experiment",           "NormalExperiment"),
    }

    def _load_experiment_module(self, experiment_name: str) -> BaseExperiment:
        """
        Load and instantiate the experiment class for the given experiment name.

        Resolves the module and class via REGISTRY for explicit, validated discovery.
        """
        if experiment_name not in self.REGISTRY:
            available = ", ".join(sorted(self.REGISTRY.keys()))
            self.logger.error(
                f"Unknown experiment '{experiment_name}'. "
                f"Available experiments: {available}"
            )
            sys.exit(1)

        module_name, class_name = self.REGISTRY[experiment_name]

        try:
            self.logger.debug(f"Loading {class_name} from {module_name}")
            module = importlib.import_module(module_name)
            experiment_class = getattr(module, class_name)

            return experiment_class(
                name=class_name,
                config=self.config_manager.config,
                logger=self.logger,
            )
        except ModuleNotFoundError:
            self.logger.error(f"Module '{module_name}' not found. Ensure the file exists in the experiments/ directory.")
            sys.exit(1)
        except AttributeError:
            self.logger.error(f"Class '{class_name}' not found inside module '{module_name}'.")
            sys.exit(1)
        except Exception as e:
            self.logger.error(f"Failed to load experiment module '{experiment_name}': {e}")
            sys.exit(1)


    def execute(self) -> None:
        """
        Loads the configured experiment and safely manages its execution lifecycle.
        """
        experiment_name = self.config_manager.get("experiment", "Replay")
        self.logger.info(f"Preparing to execute {experiment_name} Experiment...")
        
        # 1. Load Experiment
        experiment_instance = self._load_experiment_module(experiment_name)
        
        # 2. Scheduling (optional delay before start)
        delay_sec = self.config_manager.get("schedule_delay_sec", 0)
        if delay_sec > 0:
            self.logger.info(f"Scheduling: Waiting {delay_sec} seconds before initialization...")
            time.sleep(delay_sec)
        
        try:
            # 3. Mark Dataset Start
            self.dataset_sync.mark_start()
            
            # 4. Initialization
            self.logger.info(f"[{experiment_instance.name}] Initializing...")
            experiment_instance.initialize()
            
            # 4. Set IPC Label (Start Attack Labelling)
            self.logger.info(f"[{experiment_instance.name}] Injecting Attack Label to Edge Node IPC...")
            self.label_manager.set_label(experiment_instance.name)
            
            # 5. Run Experiment
            self.logger.info(f"[{experiment_instance.name}] Running experiment logic...")
            experiment_instance.run()
            
        except Exception as e:
            self.logger.error(f"[{experiment_instance.name}] Encountered unhandled exception during run: {e}")
            
        finally:
            # 6. Revert IPC Label
            self.logger.info(f"[{experiment_instance.name}] Reverting Attack Label to 'Normal'...")
            self.label_manager.reset()
            
            # 7. Cleanup
            self.logger.info(f"[{experiment_instance.name}] Cleaning up...")
            try:
                experiment_instance.cleanup()
            except Exception as e:
                self.logger.error(f"[{experiment_instance.name}] Cleanup failed: {e}")
                
            # 8. Dataset Synchronization
            self.logger.info(f"[{experiment_instance.name}] Synchronizing Datasets...")
            self.dataset_sync.sync_datasets(experiment_name)
            
            self.logger.info(f"[{experiment_instance.name}] Lifecycle complete.")
