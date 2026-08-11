"""
=============================================================================
 base_experiment.py
 Abstract base class for all cybersecurity experiments in the IIoT testbed.
=============================================================================
 Provides:
   - Mandatory lifecycle interface (initialize / run / cleanup).
   - Automatic experiment_config property with standard timing fields.
   - Protected lifecycle log helpers so all experiments produce uniform log output.
=============================================================================
"""

from abc import ABC, abstractmethod
import logging
import time


class BaseExperiment(ABC):
    """
    Abstract interface for cybersecurity experiments in the IIoT research testbed.

    All experiments must inherit from this class and implement the three lifecycle
    methods: initialize(), run(), cleanup().

    The ExperimentManager orchestrates the lifecycle and guarantees that cleanup()
    is always called, even if run() raises an exception.

    Label management and dataset synchronization are handled externally by the
    ExperimentManager; individual experiments do not interact with either directly.
    """

    def __init__(self, name: str, config: dict, logger: logging.Logger):
        """
        Initialise the base experiment state.

        Args:
            name   : Canonical name of the experiment class (e.g. "ReplayExperiment").
            config : Full framework configuration dictionary provided by ConfigManager.
            logger : Shared framework Logger instance.
        """
        self.name   = name
        self.config = config
        self.logger = logger

    # ------------------------------------------------------------------
    # experiment_config — standardised per-experiment parameters
    # ------------------------------------------------------------------

    @property
    def experiment_config(self) -> dict:
        """
        Return the experiment-specific configuration block from the global config.

        Looks for a key matching the experiment's own name inside the top-level
        ``experiments`` dictionary. If not found, returns a default configuration
        so that every experiment has a consistent set of timing parameters without
        requiring manual config edits for initial runs.

        Standard keys:
            experiment_name       (str)   : Human-readable experiment label.
            pre_attack_duration   (float) : Seconds to observe baseline before starting.
            attack_duration       (float) : Duration of the active experiment phase.
            post_attack_duration  (float) : Seconds to monitor after the experiment ends.
            description           (str)   : One-line description of the experiment purpose.
        """
        experiments = self.config.get("experiments", {})
        return experiments.get(
            self.name,
            {
                "experiment_name":      self.name,
                "pre_attack_duration":  5.0,
                "attack_duration":      30.0,
                "post_attack_duration": 5.0,
                "description":          "No description provided.",
            },
        )

    # ------------------------------------------------------------------
    # Lifecycle log helpers (shared, non-overridable)
    # ------------------------------------------------------------------

    def _log_initialized(self) -> None:
        """Log a uniform initialization confirmation message."""
        self.logger.info(f"[{self.name}] Experiment initialized.")

    def _log_started(self) -> None:
        """Log a uniform experiment-started message."""
        self.logger.info(f"[{self.name}] Experiment started.")

    def _log_completed(self) -> None:
        """Log a uniform experiment-completed message."""
        self.logger.info(f"[{self.name}] Experiment completed.")

    def _log_cleaned_up(self) -> None:
        """Log a uniform cleanup-complete message."""
        self.logger.info(f"[{self.name}] Experiment cleaned up.")

    # ------------------------------------------------------------------
    # Abstract lifecycle methods — must be implemented by every subclass
    # ------------------------------------------------------------------

    @abstractmethod
    def initialize(self) -> None:
        """
        Setup phase: load resources, open files, configure parameters.
        Must be called before run(). Implementations should call
        self._log_initialized() at the end of a successful setup.
        """

    @abstractmethod
    def run(self) -> None:
        """
        Execution phase: the primary experiment logic runs here.
        This method blocks the caller until the experiment is complete.
        Implementations should call self._log_started() at the beginning and
        self._log_completed() at the end.
        """

    @abstractmethod
    def cleanup(self) -> None:
        """
        Teardown phase: release all resources allocated during initialize().
        Guaranteed to be called by the ExperimentManager even if run() raises.
        Implementations should call self._log_cleaned_up() at the end.
        """
