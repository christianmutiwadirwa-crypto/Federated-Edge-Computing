"""
=============================================================================
 InferenceEngine.py
 Real-time attack classification thread for the Federated IDS pipeline.
=============================================================================
 Runs as a background thread inside the Edge Node server. Consumes a
 queue of completed feature windows produced by the WindowManager, applies
 the exact same feature transformations used at training time (via
 FeatureTransformer), and classifies each window using the trained MLP.

 When an attack is detected, it forwards the alert to AlertManager.

 Design principles:
   - STATEFUL: maintains a FeatureTransformer instance to compute diffs
     across consecutive windows, matching the training-time behaviour.
   - FAULT-TOLERANT: if the model file is missing, the thread logs a warning
     and passes all windows through as 'Normal' (fail-open for availability).
   - HOT-RELOADABLE: call reload_model() after receiving a new global model
     from the FL Server to swap the weights without restarting the server.
=============================================================================
"""

import threading
import queue
import warnings
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional


# Default paths — can be overridden via config
DEFAULT_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"


class InferenceEngine(threading.Thread):
    """
    Background thread that classifies completed feature windows in real time.

    Args:
        inference_queue: Thread-safe queue that WindowManager pushes windows onto.
                         Each item is a dict: {'cyber': {...}, 'physical': {...},
                                               'window_timestamp': str, 'node_id': int}
        alert_manager:   AlertManager instance to receive attack notifications.
        models_dir:      Directory containing fused_ids_model.pkl, scaler.pkl,
                         label_encoder.pkl, feature_columns.pkl.
        logger:          Logger instance from the EdgeNode framework.
    """

    def __init__(
        self,
        inference_queue: queue.Queue,
        alert_manager,
        models_dir: Path = DEFAULT_MODELS_DIR,
        logger=None,
    ):
        super().__init__(daemon=True, name="InferenceEngine")
        self._queue         = inference_queue
        self._alert_manager = alert_manager
        self._models_dir    = Path(models_dir)
        self._logger        = logger
        self._stop_event    = threading.Event()
        self._lock          = threading.Lock()

        # Model artifacts — loaded by _load_model()
        self._model          = None
        self._scaler         = None
        self._label_encoder  = None
        self._feature_columns = None
        self._model_ready    = False

        # Iso Forest artifacts
        self._iso_model          = None
        self._iso_scaler         = None
        self._iso_feature_columns = None
        self._iso_model_ready    = False

        # FeatureTransformer maintains rolling diff state
        # Import here to avoid circular imports at module load time
        from FeatureTransformer import FeatureTransformer
        self._transformer = FeatureTransformer()

        self._load_model()

    # ------------------------------------------------------------------
    # Model Loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """
        Load all model artifacts from disk.
        Silently sets _model_ready=False if any artifact is missing.
        """
        required = {
            "fused_ids_model.pkl":  "_model",
            "scaler.pkl":           "_scaler",
            "label_encoder.pkl":    "_label_encoder",
            "feature_columns.pkl":  "_feature_columns",
        }

        try:
            for filename, attr in required.items():
                path = self._models_dir / filename
                if not path.exists():
                    self._log(f"[InferenceEngine] Missing artifact: {path}. "
                              "Inference disabled until model is deployed.", level="warning")
                    self._model_ready = False
                    return
                setattr(self, attr, joblib.load(path))

            self._model_ready = True
            self._log(
                f"[InferenceEngine] Model loaded. "
                f"Classes: {list(self._label_encoder.classes_)} | "
                f"Features: {len(self._feature_columns)}"
            )
        except Exception as exc:
            self._log(f"[InferenceEngine] Failed to load model: {exc}", level="error")
            self._model_ready = False

        # Load Isolation Forest
        required_iso = {
            "iso_forest_model.pkl":     "_iso_model",
            "iso_scaler.pkl":           "_iso_scaler",
            "iso_physical_columns.pkl": "_iso_feature_columns",
        }
        self._iso_model_ready = False
        try:
            for filename, attr in required_iso.items():
                path = self._models_dir / filename
                if not path.exists():
                    self._log(f"[InferenceEngine] Missing Isolation Forest artifact: {path}. "
                              "Physical anomaly detection disabled.", level="warning")
                    raise FileNotFoundError()
                setattr(self, attr, joblib.load(path))
            
            self._iso_model_ready = True
            self._log(f"[InferenceEngine] Isolation Forest loaded. "
                      f"Features: {len(self._iso_feature_columns)}")
        except Exception as exc:
            pass

    def reload_model(self) -> None:
        """
        Hot-reload the model from disk after the FL Server broadcasts new weights.
        Thread-safe: acquires lock so in-flight predictions complete cleanly.
        """
        self._log("[InferenceEngine] Reloading model from disk...")
        with self._lock:
            self._transformer.reset()
            self._load_model()
        self._log("[InferenceEngine] Model reload complete.")

    # ------------------------------------------------------------------
    # Thread Main Loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._log("[InferenceEngine] Started.")

        while not self._stop_event.is_set():
            try:
                window = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                self._process_window(window)
            except Exception as exc:
                self._log(f"[InferenceEngine] Error processing window: {exc}", level="error")
            finally:
                self._queue.task_done()

        self._log("[InferenceEngine] Stopped.")

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Window Processing
    # ------------------------------------------------------------------

    def _process_window(self, window: dict) -> None:
        """
        Classify one window and fire an alert if an attack is detected.

        Window dict format:
            {
                'cyber':             dict  (from CyberFeatureExtractor.extract()),
                'physical':          dict  (from PhysicalCSVWriter row, or None),
                'window_timestamp':  str   (ISO timestamp string),
                'node_id':           int,
            }
        """
        if not self._model_ready:
            return

        cyber    = window.get("cyber", {})
        physical = window.get("physical", None)
        ts       = window.get("window_timestamp", "unknown")
        node_id  = window.get("node_id", 0)

        # --- Isolation Forest (Independent Physical Anomaly Detection) ---
        iso_anomaly_detected = False
        if self._iso_model_ready and physical:
            iso_vec = self._align_iso_features(physical)
            if iso_vec is not None:
                iso_df = pd.DataFrame(iso_vec.reshape(1, -1), columns=self._iso_feature_columns)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    iso_scaled = self._iso_scaler.transform(iso_df)
                iso_pred = self._iso_model.predict(iso_scaled)[0]
                if iso_pred == -1:
                    iso_anomaly_detected = True
                    self._alert_manager.alert(
                        label="Physical_Anomaly",
                        confidence=1.0,
                        window_timestamp=ts,
                        node_id=node_id,
                    )

        with self._lock:
            # Apply feature engineering (diffs + metadata strip)
            raw_vector, feature_keys = self._transformer.transform_window(
                cyber_features=cyber,
                physical_features=physical,
            )

        # Align to the exact column order the model was trained on
        feature_vector = self._align_features(raw_vector, feature_keys)
        if feature_vector is None:
            return

        # Scale and predict — wrap in DataFrame so column names match the
        # StandardScaler that was fitted on a named DataFrame at training time.
        feature_df = pd.DataFrame(
            feature_vector.reshape(1, -1),
            columns=self._feature_columns,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            scaled = self._scaler.transform(feature_df)
        proba  = self._model.predict_proba(scaled)[0]
        pred_idx   = int(np.argmax(proba))
        confidence = float(proba[pred_idx])
        label      = self._label_encoder.classes_[pred_idx]

        if label != "Normal":
            self._alert_manager.alert(
                label=label,
                confidence=confidence,
                window_timestamp=ts,
                node_id=node_id,
            )
        else:
            if not iso_anomaly_detected:
                self._alert_manager.log_normal(window_timestamp=ts, node_id=node_id)

    def _align_iso_features(self, physical: dict) -> Optional[np.ndarray]:
        """Align physical dictionary to expected Isolation Forest columns."""
        if not physical or not self._iso_feature_columns:
            return None
        aligned = np.array(
            [float(physical.get(col, 0.0)) for col in self._iso_feature_columns],
            dtype=np.float32,
        )
        return aligned

    def _align_features(
        self,
        raw_vector: np.ndarray,
        feature_keys: list,
    ) -> Optional[np.ndarray]:
        """
        Re-order the feature vector to match the exact column order the
        model was trained on (stored in feature_columns.pkl).

        If a feature is missing from the incoming window, it is filled with 0.0.
        This ensures the engine does not crash if new features are added later.
        """
        if self._feature_columns is None:
            return raw_vector

        key_to_val = dict(zip(feature_keys, raw_vector))
        aligned = np.array(
            [key_to_val.get(col, 0.0) for col in self._feature_columns],
            dtype=np.float32,
        )
        return aligned

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------

    def _log(self, message: str, level: str = "info") -> None:
        # Map standard level names to the custom Logger's severity strings
        severity_map = {
            "info":    "INFO",
            "warning": "WARNING",
            "error":   "ERROR",
            "debug":   "DEBUG",
        }
        severity = severity_map.get(level.lower(), "INFO")

        if self._logger:
            self._logger.log(message, severity=severity)
        else:
            print(message)
