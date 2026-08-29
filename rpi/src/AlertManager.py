"""
=============================================================================
 AlertManager.py
 Attack alert handler for the Federated IDS pipeline.
=============================================================================
 Receives attack predictions from the InferenceEngine and persists them
 to a structured log file. Designed to be extended with HTTP callbacks
 to a central dashboard in a future phase.
=============================================================================
"""

import os
import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class AlertManager:
    """
    Thread-safe alert handler that persists attack predictions to disk.

    Usage:
        alert_manager = AlertManager(alerts_dir="alerts/")
        alert_manager.alert(
            label="FloodingExperiment",
            confidence=0.9981,
            window_timestamp="2026-08-25 12:00:00.000000",
            node_id=1,
        )
    """

    def __init__(self, alerts_dir: str = "alerts"):
        self._alerts_dir = Path(alerts_dir)
        self._alerts_dir.mkdir(parents=True, exist_ok=True)
        self._log_path   = self._alerts_dir / "alerts.log"
        self._lock       = threading.Lock()
        self._alert_count = 0

    def alert(
        self,
        label: str,
        confidence: float,
        window_timestamp: str,
        node_id: int = 0,
    ) -> None:
        """
        Record a detected attack.

        Args:
            label:            Predicted attack class (e.g. 'FloodingExperiment').
            confidence:       Model confidence score [0.0, 1.0].
            window_timestamp: ISO timestamp of the window that triggered the alert.
            node_id:          ID of the Edge Node that detected the attack.
        """
        now_utc = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        alert_record = {
            "alert_time":       now_utc,
            "window_time":      window_timestamp,
            "node_id":          node_id,
            "attack_label":     label,
            "confidence":       round(confidence, 6),
        }

        log_line = (
            f"[{now_utc}] "
            f"[NODE {node_id}] "
            f"ATTACK DETECTED: {label:<30} "
            f"confidence={confidence:.2%}"
        )

        with self._lock:
            self._alert_count += 1
            # Append to human-readable log
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")

            # Append to machine-readable JSONL file for dashboard ingestion
            jsonl_path = self._alerts_dir / "alerts.jsonl"
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert_record) + "\n")

        print(f"[ALERT] {log_line}")

    def log_normal(self, window_timestamp: str, node_id: int = 0) -> None:
        """
        Optionally log a Normal (safe) prediction for audit trail purposes.
        Writes to a separate predictions.log — not the alerts log.
        """
        now_utc = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        log_line = f"[{now_utc}] [NODE {node_id}] Normal  (window: {window_timestamp})\n"

        pred_path = self._alerts_dir / "predictions.log"
        with self._lock:
            with open(pred_path, "a", encoding="utf-8") as f:
                f.write(log_line)

    @property
    def alert_count(self) -> int:
        """Total number of attack alerts fired since startup."""
        return self._alert_count
