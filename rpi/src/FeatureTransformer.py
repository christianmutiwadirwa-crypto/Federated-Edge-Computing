"""
=============================================================================
 FeatureTransformer.py
 Shared feature engineering utility for the Federated IDS pipeline.
=============================================================================
 This module is the single source of truth for all feature engineering
 logic. Both the training pipeline (train_fused_model.py) and the
 real-time InferenceEngine import this class to guarantee that the exact
 same transformations are applied at training time and at inference time.

 Prevents training/serving skew — a silent bug where the model is trained
 on features computed one way but receives features computed a different
 way at inference time.

 Responsibilities:
   - Define the exact set of CYBER_METADATA columns to drop.
   - Define the exact set of PHYSICAL_METADATA columns to drop.
   - Compute temporal _diff features on key cyber metrics.
   - Maintain a rolling buffer of the previous window's values for diffs.
   - Produce a final, ordered, clean numpy array ready for model inference.
=============================================================================
"""

import numpy as np
import pandas as pd
from collections import deque
from typing import Optional


# ---------------------------------------------------------------------------
# Column Definitions — Single Source of Truth
# ---------------------------------------------------------------------------

# Identifier/metadata columns that must be stripped before training or inference.
# These columns encode experiment identity, not attack patterns.
CYBER_METADATA_COLS = [
    "window_id",
    "window_start_time",
    "window_end_time",
    "node_id",
    "src_ip",
    "dst_ip",
    "src_port",
    "dst_port",
    "AttackLabel",
]

PHYSICAL_METADATA_COLS = [
    "Timestamp",
    "Node ID",
    "Label",
]

# Cyber features on which temporal diff is computed.
# NOTE: These were disabled because the ESP32's 2-second sample window and the
# server's 2-second tumbling window run unsynchronised. This causes a permanent
# ±0.5 aliasing sawtooth in packet_rate_diff, which the model learned to
# associate with attack classes, producing false positives on every other window.
# Low importance (ranked 11th and 14th of 29 features) — not worth the noise.
DIFF_FEATURE_COLS: list = []


class FeatureTransformer:
    """
    Stateful feature transformer that maintains a rolling window of the
    previous cyber feature vector so that temporal diff features can be
    computed consistently at both training time and inference time.

    Usage at training time:
        transformer = FeatureTransformer()
        transformed_df = transformer.fit_transform_dataframe(merged_df)

    Usage at inference time (called once per incoming window):
        transformer = FeatureTransformer()   # one instance per node
        feature_vector = transformer.transform_window(cyber_dict, phys_dict)
    """

    def __init__(self):
        # Rolling buffer: stores the previous window's values for diff cols.
        self._prev_values: dict = {col: 0.0 for col in DIFF_FEATURE_COLS}
        self._is_first_window: bool = True

    # ------------------------------------------------------------------
    # Training-time API: transforms a full merged DataFrame at once
    # ------------------------------------------------------------------

    def fit_transform_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform a full merged Cyber+Physical DataFrame as used in
        train_fused_model.py.

        Steps:
          1. Sort by window_start_time so diffs are chronologically meaningful.
          2. Compute _diff features using pandas diff() (efficient vectorized op).
          3. Drop all metadata columns.
          4. Drop rows with NaN values (first row of each experiment after diff).

        Args:
            df: Merged DataFrame containing both cyber and physical columns,
                including 'AttackLabel' and all metadata columns.

        Returns:
            Clean DataFrame with only model-input features + 'AttackLabel'.
        """
        df = df.copy()

        # Sort chronologically within each experiment group so diffs are valid
        if "window_start_time" in df.columns:
            df["window_start_time"] = pd.to_datetime(df["window_start_time"])
            df = df.sort_values("window_start_time").reset_index(drop=True)

        # Compute temporal diffs
        for col in DIFF_FEATURE_COLS:
            if col in df.columns:
                df[f"{col}_diff"] = df[col].diff().fillna(0.0)

        # Preserve AttackLabel before dropping metadata
        labels = df["AttackLabel"].copy() if "AttackLabel" in df.columns else None

        # Drop all metadata columns (ignore missing ones silently)
        cols_to_drop = [c for c in CYBER_METADATA_COLS + PHYSICAL_METADATA_COLS
                        if c in df.columns]
        df = df.drop(columns=cols_to_drop)

        # Re-attach label for downstream balancing / splitting
        if labels is not None:
            df["AttackLabel"] = labels.values

        # Drop any rows with NaN (can occur at group boundaries)
        df = df.dropna().reset_index(drop=True)

        return df

    # ------------------------------------------------------------------
    # Inference-time API: transforms a single incoming window
    # ------------------------------------------------------------------

    def transform_window(
        self,
        cyber_features: dict,
        physical_features: Optional[dict] = None,
    ) -> np.ndarray:
        """
        Transform a single incoming window at inference time.

        This method maintains internal state (_prev_values) to compute
        temporal diffs across consecutive calls, exactly matching the
        pandas diff() behaviour used during training.

        Args:
            cyber_features:    Dict of cyber feature values (as produced by
                               CyberFeatureExtractor.extract()).
            physical_features: Dict of physical feature values (as produced
                               by PhysicalCSVWriter). Pass None if running
                               cyber-only inference.

        Returns:
            1-D numpy float32 array ready to be passed to model.predict().
        """
        combined = {}

        # --- Cyber features ---
        for key, val in cyber_features.items():
            if key not in CYBER_METADATA_COLS:
                combined[key] = float(val) if val is not None else 0.0

        # --- Physical features ---
        if physical_features is not None:
            for key, val in physical_features.items():
                if key not in PHYSICAL_METADATA_COLS:
                    combined[key] = float(val) if val is not None else 0.0

        # --- Temporal diff features ---
        for col in DIFF_FEATURE_COLS:
            current_val = combined.get(col, 0.0)
            if self._is_first_window:
                combined[f"{col}_diff"] = 0.0
            else:
                combined[f"{col}_diff"] = current_val - self._prev_values[col]
            self._prev_values[col] = current_val
            
        self._is_first_window = False

        # Build sorted feature vector (alphabetical sort guarantees
        # the same column order as the training DataFrame)
        feature_keys = sorted(k for k in combined if k != "AttackLabel")
        vector = np.array([combined[k] for k in feature_keys], dtype=np.float32)

        return vector, feature_keys

    def reset(self):
        """
        Reset the rolling diff buffer.
        Call this when a new TCP session starts to avoid computing diffs
        across session boundaries.
        """
        self._prev_values = {col: 0.0 for col in DIFF_FEATURE_COLS}
        self._is_first_window = True
