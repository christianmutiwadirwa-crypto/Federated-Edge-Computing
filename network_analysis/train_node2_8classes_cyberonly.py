"""
=============================================================================
 train_node2_8classes_cyberonly.py
 Federated Learning Node 2 Local Training Pipeline (8 Classes, Cyber-Only)
=============================================================================
 Produces a trained MLP model on an 8-class subset using ONLY cyber network
 features (no physical accelerometer data). Physical features have been
 shown to cause false positive cyber alerts when the machine's physical
 state deviates from the training baseline.

 Feature analysis confirmed that the 29 cyber-derived features alone
 achieve 99% accuracy separating all 8 classes including SlowDoS/Normal/
 ConnectionReset which previously motivated the physical feature fusion.

 Output: models/fused_ids_model.pkl  (drop-in replacement for the fused model)
         models/scaler.pkl
         models/label_encoder.pkl
         models/feature_columns.pkl
         models/class_counts.json
=============================================================================
"""

import sys
import argparse
import joblib
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from imblearn.over_sampling import SMOTE

# FeatureTransformer lives in rpi/src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rpi" / "src"))
from FeatureTransformer import FeatureTransformer


# ---------------------------------------------------------------------------
# Configuration & Global Schema
# ---------------------------------------------------------------------------

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent.parent / "rpi" / "experiments" / "results"
DEFAULT_OUTPUT_DIR  = Path(__file__).resolve().parent.parent / "models"

MLP_HIDDEN_LAYERS   = (100, 50)
MLP_MAX_ITER        = 500
RANDOM_STATE        = 42
TEST_SIZE           = 0.20

# Global 11-class schema — output layer is fixed at 11 neurons for FL compatibility
GLOBAL_CLASSES = {
    'ConnectionResetExperiment': 0,
    'DataTamperingExperiment':   1,
    'DelayExperiment':           2,
    'DeviceSpoofExperiment':     3,
    'DuplicatePacketExperiment': 4,
    'FloodingExperiment':        5,
    'Normal':                    6,
    'PacketInjectionExperiment': 7,
    'PacketLossExperiment':      8,
    'ReplayExperiment':          9,
    'SlowDoSExperiment':         10
}

# 8 classes Node 2 trains on (excludes ConnectionReset, DataTampering, Delay)
ALLOWED_CLASSES = [
    'Normal',
    'ReplayExperiment',
    'SlowDoSExperiment',
    'PacketInjectionExperiment',
    'DeviceSpoofExperiment',
    'PacketLossExperiment',
    'DuplicatePacketExperiment',
    'FloodingExperiment',
]


# ---------------------------------------------------------------------------
# Step 1: Load cyber-only dataset (NO physical merge)
# ---------------------------------------------------------------------------

def load_cyber_only_dataset(results_dir: Path) -> pd.DataFrame:
    """
    Load cyber_data.csv files only — physical_data.csv is intentionally excluded.
    """
    cyber_files = sorted(results_dir.rglob("cyber_data.csv"))
    if not cyber_files:
        raise FileNotFoundError(f"No cyber_data.csv files found under: {results_dir}")

    dfs = []
    skipped = 0
    for cyber_path in cyber_files:
        experiment_name = cyber_path.parent.name
        try:
            cyber_df = pd.read_csv(cyber_path)
            cyber_df["window_start_time"] = pd.to_datetime(cyber_df["window_start_time"])
            cyber_df = cyber_df.sort_values("window_start_time").reset_index(drop=True)
            cyber_df["AttackLabel"] = cyber_df["AttackLabel"].replace("NormalExperiment", "Normal")
            dfs.append(cyber_df)
            print(f"  Loaded: {experiment_name} ({len(cyber_df)} rows)")
        except Exception as exc:
            print(f"  [!] Skipping {experiment_name}: {exc}")
            skipped += 1

    if not dfs:
        raise RuntimeError("No valid cyber_data.csv files could be loaded.")

    master = pd.concat(dfs, ignore_index=True)
    master["AttackLabel"] = master["AttackLabel"].replace("NormalExperiment", "Normal")

    print(f"\n  Total rows before class filter: {len(master)}")
    print(f"  All classes found: {sorted(master['AttackLabel'].unique())}")

    # --- NOISE CLEANING ---
    # Many cyber attack experiments contain windows of perfectly normal background traffic.
    # If we don't drop them, SMOTE will synthesize attack labels directly on top of the 
    # Normal cluster, causing massive false positives in production.
    clean_masks = []
    
    # 1. Normal is always kept
    clean_masks.append(master["AttackLabel"] == "Normal")
    
    # 2. DataTampering MUST have evidence of tampering (otherwise it's indistinguishable from Normal)
    dt_mask = (master["AttackLabel"] == "DataTamperingExperiment") & \
              ((master["crc_failure_count"] > 0) | (master["invalid_packet_count"] > 0))
    clean_masks.append(dt_mask)
    
    # 3. All other high-rate attacks (Delay, Flooding, Spoof, etc.) must have total_packets > 2.
    # (Normal traffic on the ESP32 produces exactly 1-2 packets per 2s window).
    other_attacks = master["AttackLabel"].isin([
        "DelayExperiment", "ConnectionResetExperiment", "DuplicatePacketExperiment", 
        "FloodingExperiment", "DeviceSpoofExperiment", "PacketLossExperiment"
    ])
    other_mask = other_attacks & (master["total_packets"] > 2)
    clean_masks.append(other_mask)
    
    # Combine masks
    final_mask = pd.concat(clean_masks, axis=1).any(axis=1)
    master = master[final_mask].reset_index(drop=True)
    print(f"  Rows after dropping noisy 'Normal' windows from attack classes: {len(master)}")

    # Filter to only the 8 allowed classes for Node 2
    master = master[master["AttackLabel"].isin(ALLOWED_CLASSES)]
    print(f"  Rows after filtering to 8 classes: {len(master)}")
    print(f"\n  Class distribution:")
    print(master["AttackLabel"].value_counts().to_string())

    return master


# ---------------------------------------------------------------------------
# Step 2: Feature Engineering (cyber features + EWMA diffs)
# ---------------------------------------------------------------------------

def engineer_features(master_df: pd.DataFrame) -> pd.DataFrame:
    """Run FeatureTransformer to compute EWMA diffs. Returns cyber-only features."""
    transformer = FeatureTransformer()
    transformed = transformer.fit_transform_dataframe(master_df)

    # Drop any physical columns that might have leaked in
    physical_cols = ["AccX", "AccY", "AccZ", "Magnitude", "Timestamp",
                     "acc_x", "acc_y", "acc_z", "magnitude"]
    cols_to_drop = [c for c in physical_cols if c in transformed.columns]
    if cols_to_drop:
        print(f"  [*] Dropping residual physical columns: {cols_to_drop}")
        transformed = transformed.drop(columns=cols_to_drop)

    print(f"  [*] Final feature count: {transformed.shape[1] - 1} cyber features")
    return transformed


# ---------------------------------------------------------------------------
# Step 3: Split, Scale, Train with SMOTE
# ---------------------------------------------------------------------------

def train(df: pd.DataFrame):
    X = df.drop(columns=["AttackLabel"])
    feature_names = list(X.columns)

    # Map string labels to global integer schema
    y_encoded = df["AttackLabel"].map(GLOBAL_CLASSES).values

    # Record class counts BEFORE SMOTE (for FL server-side weighting)
    class_counts = [0] * len(GLOBAL_CLASSES)
    for label_int in y_encoded:
        class_counts[int(label_int)] += 1

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y_encoded,
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    print("\n  Applying SMOTE to balance classes in the training set...")
    smote = SMOTE(random_state=RANDOM_STATE)
    X_train_resampled, y_train_resampled = smote.fit_resample(X_train_scaled, y_train)

    print(f"\n  Training MLP on {len(X_train_resampled)} samples (balanced via SMOTE), "
          f"{X_train_resampled.shape[1]} cyber features, "
          f"forcing 11 output neurons for FL compatibility...")

    clf = MLPClassifier(
        hidden_layer_sizes=MLP_HIDDEN_LAYERS,
        max_iter=MLP_MAX_ITER,
        random_state=RANDOM_STATE,
        verbose=True,
    )

    all_classes = np.arange(len(GLOBAL_CLASSES))
    # First call initialises the network weights
    clf.partial_fit(X_train_resampled, y_train_resampled, classes=all_classes)

    # Continue iterating until max_iter
    for iteration in range(1, MLP_MAX_ITER):
        clf.partial_fit(X_train_resampled, y_train_resampled)
        if clf.loss_ < 1e-4:
            print(f"  Converged at iteration {iteration + 1} (loss={clf.loss_:.6f})")
            break

    # Evaluate
    y_pred = clf.predict(X_test_scaled)
    acc    = accuracy_score(y_test, y_pred)

    # Build a label encoder purely for report display (maps int → class name)
    int_to_label = {v: k for k, v in GLOBAL_CLASSES.items()}
    present_ints  = sorted(set(y_test) | set(y_pred))
    present_names = [int_to_label[i] for i in present_ints]
    le = LabelEncoder()
    le.classes_ = np.array([int_to_label[i] for i in range(len(GLOBAL_CLASSES))])

    print(f"\n  Test Accuracy: {acc * 100:.2f}%")
    print("\n  Classification Report:")
    print(classification_report(y_test, y_pred,
                                labels=present_ints,
                                target_names=present_names,
                                zero_division=0))
    print("  Confusion Matrix:")
    cm = confusion_matrix(y_test, y_pred, labels=present_ints)
    cm_df = pd.DataFrame(cm, index=present_names, columns=present_names)
    print(cm_df.to_string())

    return clf, scaler, le, feature_names, class_counts, acc


# ---------------------------------------------------------------------------
# Step 4: Persist Artifacts
# ---------------------------------------------------------------------------

def save_artifacts(
    clf, scaler, le, feature_names, class_counts, output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(clf,          output_dir / "fused_ids_model.pkl")
    joblib.dump(scaler,       output_dir / "scaler.pkl")
    joblib.dump(le,           output_dir / "label_encoder.pkl")
    joblib.dump(feature_names, output_dir / "feature_columns.pkl")

    with open(output_dir / "class_counts.json", "w") as f:
        json.dump(class_counts, f)

    print(f"\n  Artifacts saved to: {output_dir}")
    print(f"    fused_ids_model.pkl  ({(output_dir / 'fused_ids_model.pkl').stat().st_size // 1024} KB)")
    print(f"    scaler.pkl")
    print(f"    label_encoder.pkl")
    print(f"    feature_columns.pkl  ({len(feature_names)} cyber features)")
    print(f"    class_counts.json    {class_counts}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train cyber-only 8-class Node 1 model")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output-dir",  type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    print("=" * 65)
    print(" Node 2 Training: Cyber-Only MLP (8 classes, 11 neurons)")
    print(f" Results dir: {args.results_dir}")
    print(f" Output dir:  {args.output_dir}")
    print(f" Started:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    print("\n[Step 1] Loading cyber-only dataset...")
    master = load_cyber_only_dataset(args.results_dir)

    print("\n[Step 2] Engineering features...")
    df = engineer_features(master)

    print("\n[Step 3] Training MLP...")
    clf, scaler, le, feature_names, class_counts, acc = train(df)

    print("\n[Step 4] Saving artifacts...")
    save_artifacts(clf, scaler, le, feature_names, class_counts, args.output_dir)

    print("\n" + "=" * 65)
    print(f" Training Complete! Final accuracy: {acc * 100:.2f}%")
    print(f" Model type: Cyber-Only MLP (no physical features)")
    print(f" Compatible with FL server (11-neuron output layer)")
    print("=" * 65)


if __name__ == "__main__":
    main()
