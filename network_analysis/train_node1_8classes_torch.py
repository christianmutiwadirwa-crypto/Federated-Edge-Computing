"""
=============================================================================
 train_node1_8classes_torch.py
 Federated Learning Node 1 — PyTorch Training Pipeline (8 Classes, Cyber-Only)
=============================================================================
 Class-Aware Federated Learning with Global Knowledge Preservation.

 Key mechanisms:
   1. Output neuron freezing   : gradients for Replay/PacketInjection/SlowDoS
                                 are zeroed before the optimiser step.
   2. Knowledge distillation   : hidden layers are penalised for drifting from
                                 the teacher (global) model's soft predictions.
   3. FedProx regularisation   : a proximal term limits total weight drift.

 Outputs:
   models/fused_ids_model.pth   — PyTorch checkpoint (weights + arch metadata)
   models/class_counts.json     — per-class sample counts for FL server
   models/scaler.pkl            — unchanged (global scaler already synced)
   models/label_encoder.pkl     — unchanged
   models/feature_columns.pkl   — unchanged
=============================================================================
"""

import sys
import argparse
import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from imblearn.over_sampling import SMOTE

# FeatureTransformer and mlp_torch live alongside this script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rpi" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from FeatureTransformer import FeatureTransformer
from mlp_torch import (
    FederatedMLP, save_model, load_model,
    federated_loss,
)


# ---------------------------------------------------------------------------
# Configuration & Global Schema
# ---------------------------------------------------------------------------

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent.parent / "rpi" / "experiments" / "results"
DEFAULT_OUTPUT_DIR  = Path(__file__).resolve().parent.parent / "models"

RANDOM_STATE  = 42
TEST_SIZE     = 0.20
LOCAL_EPOCHS  = 1          # Critical: 1 epoch prevents catastrophic forgetting
BATCH_SIZE    = 256
LEARNING_RATE = 1e-3
LAMBDA_KD     = 0.5        # Knowledge distillation weight
MU_PROX       = 0.01       # FedProx proximal weight
KD_TEMP       = 3.0        # Knowledge distillation temperature

# Global 11-class schema — output layer fixed at 11 neurons for FL compatibility
GLOBAL_CLASSES = {
    "ConnectionResetExperiment": 0,
    "DataTamperingExperiment":   1,
    "DelayExperiment":           2,
    "DeviceSpoofExperiment":     3,
    "DuplicatePacketExperiment": 4,
    "FloodingExperiment":        5,
    "Normal":                    6,
    "PacketInjectionExperiment": 7,
    "PacketLossExperiment":      8,
    "ReplayExperiment":          9,
    "SlowDoSExperiment":         10,
}

# 8 classes Node 1 trains on (excludes Replay, PacketInjection, SlowDoS)
ALLOWED_CLASSES = [
    "Normal",
    "FloodingExperiment",
    "DataTamperingExperiment",
    "DeviceSpoofExperiment",
    "DelayExperiment",
    "ConnectionResetExperiment",
    "DuplicatePacketExperiment",
    "PacketLossExperiment",
]


# ---------------------------------------------------------------------------
# Step 1: Load Dataset
# ---------------------------------------------------------------------------

def load_cyber_only_dataset(results_dir: Path) -> pd.DataFrame:
    """Load cyber_data.csv files only — physical data intentionally excluded."""
    cyber_files = sorted(results_dir.rglob("cyber_data.csv"))
    if not cyber_files:
        raise FileNotFoundError(f"No cyber_data.csv files found under: {results_dir}")

    dfs = []
    for cyber_path in cyber_files:
        experiment_name = cyber_path.parent.name
        try:
            df = pd.read_csv(cyber_path)
            df["window_start_time"] = pd.to_datetime(df["window_start_time"])
            df = df.sort_values("window_start_time").reset_index(drop=True)
            df["AttackLabel"] = df["AttackLabel"].replace("NormalExperiment", "Normal")
            dfs.append(df)
            print(f"  Loaded: {experiment_name} ({len(df)} rows)")
        except Exception as exc:
            print(f"  [!] Skipping {experiment_name}: {exc}")

    if not dfs:
        raise RuntimeError("No valid cyber_data.csv files could be loaded.")

    master = pd.concat(dfs, ignore_index=True)
    master["AttackLabel"] = master["AttackLabel"].replace("NormalExperiment", "Normal")
    print(f"\n  Total rows before class filter: {len(master)}")

    # Noise cleaning — same logic as original script
    clean_masks = [master["AttackLabel"] == "Normal"]
    dt_mask = (master["AttackLabel"] == "DataTamperingExperiment") & \
              ((master["crc_failure_count"] > 0) | (master["invalid_packet_count"] > 0))
    clean_masks.append(dt_mask)
    other_attacks = master["AttackLabel"].isin([
        "DelayExperiment", "ConnectionResetExperiment", "DuplicatePacketExperiment",
        "FloodingExperiment", "DeviceSpoofExperiment", "PacketLossExperiment",
    ])
    clean_masks.append(other_attacks & (master["total_packets"] > 2))
    final_mask = pd.concat(clean_masks, axis=1).any(axis=1)
    master = master[final_mask].reset_index(drop=True)

    # Filter to Node 1's allowed classes
    master = master[master["AttackLabel"].isin(ALLOWED_CLASSES)]
    print(f"  Rows after filtering to 8 classes: {len(master)}")
    print(f"\n  Class distribution:\n{master['AttackLabel'].value_counts().to_string()}")
    return master


# ---------------------------------------------------------------------------
# Step 2: Feature Engineering
# ---------------------------------------------------------------------------

def engineer_features(master_df: pd.DataFrame) -> pd.DataFrame:
    """Run FeatureTransformer and drop any physical columns."""
    transformer = FeatureTransformer()
    transformed = transformer.fit_transform_dataframe(master_df)
    physical_cols = ["AccX", "AccY", "AccZ", "Magnitude", "Timestamp",
                     "acc_x", "acc_y", "acc_z", "magnitude"]
    cols_to_drop = [c for c in physical_cols if c in transformed.columns]
    if cols_to_drop:
        transformed = transformed.drop(columns=cols_to_drop)
    print(f"  [*] Final feature count: {transformed.shape[1] - 1} cyber features")
    return transformed


# ---------------------------------------------------------------------------
# Step 3: Train
# ---------------------------------------------------------------------------

def train(df: pd.DataFrame, init_scaler_only: bool = False, output_dir: Path = None):
    """
    Full training pipeline.
    If init_scaler_only=True, only fits the StandardScaler and exits.
    Otherwise, runs the full PyTorch training loop.
    """
    from sklearn.preprocessing import StandardScaler

    X = df.drop(columns=["AttackLabel"])
    feature_names = list(X.columns)

    # Map string labels → global integer schema
    y_encoded = df["AttackLabel"].map(GLOBAL_CLASSES).values

    # Record class counts BEFORE SMOTE for FL server-side weighting
    class_counts = [0] * len(GLOBAL_CLASSES)
    for label_int in y_encoded:
        class_counts[int(label_int)] += 1

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y_encoded,
    )

    # ---- Scaler Init Phase ------------------------------------------------
    if init_scaler_only:
        print("\n  [Scaler Init Phase] Fitting StandardScaler on local raw data...")
        scaler = StandardScaler()
        scaler.fit(X_train)
        output_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(scaler, output_dir / "scaler.pkl")
        print(f"  Saved local scaler to {output_dir / 'scaler.pkl'}")
        return None, None, None, None, None, 0.0

    # ---- Training Phase ---------------------------------------------------
    print("\n  [Training Phase] Loading Global Scaler from models/scaler.pkl...")
    scaler = joblib.load(output_dir / "scaler.pkl")
    X_train_scaled = scaler.transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    # Sanitize NaN/inf from zero-variance features in the Global Scaler
    X_train_scaled = np.nan_to_num(X_train_scaled, nan=0.0, posinf=0.0, neginf=0.0)
    X_test_scaled  = np.nan_to_num(X_test_scaled,  nan=0.0, posinf=0.0, neginf=0.0)

    print("\n  Applying SMOTE to balance classes in the training set...")
    smote = SMOTE(random_state=RANDOM_STATE)
    X_train_resampled, y_train_resampled = smote.fit_resample(X_train_scaled, y_train)

    # Identify which global classes are missing locally
    local_class_ids  = set(int(c) for c in np.unique(y_train_resampled))
    all_class_ids    = set(range(len(GLOBAL_CLASSES)))
    missing_classes  = all_class_ids - local_class_ids
    print(f"\n  Local classes   : {sorted(local_class_ids)}")
    print(f"  Missing classes : {sorted(missing_classes)}  ← these neurons will be frozen")

    input_dim = X_train_scaled.shape[1]

    # Build student model — warm-start from global weights if available
    model_pth = output_dir / "fused_ids_model.pth"
    if model_pth.exists():
        print(f"\n  Loading global model from {model_pth.name} to warm-start training...")
        student = load_model(model_pth)
    else:
        print("\n  No global model found — initialising new PyTorch MLP from scratch...")
        student = FederatedMLP(input_dim=input_dim, hidden_sizes=(100, 50), num_classes=11)

    # Build teacher — a frozen copy of the global model for knowledge distillation
    if model_pth.exists():
        teacher = load_model(model_pth)
        teacher.eval()
        for p in teacher.parameters():
            p.requires_grad = False
    else:
        teacher = None  # No global model yet — KD term will be skipped

    # Freeze output gradients for missing classes
    student.register_class_freeze_hooks(missing_classes)

    # Snapshot the global parameters for FedProx
    global_params = [p.detach().clone() for p in student.parameters()]

    # DataLoader
    X_tensor = torch.tensor(X_train_resampled, dtype=torch.float32)
    y_tensor = torch.tensor(y_train_resampled, dtype=torch.long)
    dataset  = TensorDataset(X_tensor, y_tensor)
    loader   = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    optimizer = torch.optim.Adam(student.parameters(), lr=LEARNING_RATE)

    print(f"\n  Training PyTorch MLP: {len(X_train_resampled)} samples, "
          f"{input_dim} features, {LOCAL_EPOCHS} epoch(s)...")

    student.train()
    for epoch in range(LOCAL_EPOCHS):
        epoch_loss = 0.0
        for X_batch, y_batch in loader:
            optimizer.zero_grad()
            student_logits = student(X_batch)

            if teacher is not None:
                with torch.no_grad():
                    teacher_logits = teacher(X_batch)
                loss = federated_loss(
                    student_logits, y_batch, teacher_logits,
                    list(student.parameters()), global_params,
                    lambda_kd=LAMBDA_KD, mu=MU_PROX, T=KD_TEMP,
                )
            else:
                # First round — no global model yet, use plain CE
                import torch.nn.functional as F
                loss = F.cross_entropy(student_logits, y_batch)

            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        avg_loss = epoch_loss / len(loader)
        print(f"  Epoch {epoch + 1}/{LOCAL_EPOCHS} — Loss: {avg_loss:.6f}")

    # Evaluate on held-out test set
    student.eval()
    with torch.no_grad():
        X_test_t = torch.tensor(X_test_scaled, dtype=torch.float32)
        logits   = student(X_test_t)
        y_pred   = logits.argmax(dim=1).numpy()

    acc = accuracy_score(y_test, y_pred)
    int_to_label  = {v: k for k, v in GLOBAL_CLASSES.items()}
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
    cm    = confusion_matrix(y_test, y_pred, labels=present_ints)
    cm_df = pd.DataFrame(cm, index=present_names, columns=present_names)
    print(cm_df.to_string())

    return student, scaler, le, feature_names, class_counts, acc


# ---------------------------------------------------------------------------
# Step 4: Save Artifacts
# ---------------------------------------------------------------------------

def save_artifacts(model, scaler, le, feature_names, class_counts, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Primary model checkpoint (.pth)
    save_model(model, output_dir / "fused_ids_model.pth",
               extra_meta={"feature_names": feature_names})

    # Keep scaler, label encoder, feature columns as-is (used by test script & inference)
    joblib.dump(scaler,        output_dir / "scaler.pkl")
    joblib.dump(le,            output_dir / "label_encoder.pkl")
    joblib.dump(feature_names, output_dir / "feature_columns.pkl")

    with open(output_dir / "class_counts.json", "w") as f:
        json.dump(class_counts, f)

    print(f"\n  Saved: fused_ids_model.pth, scaler.pkl, label_encoder.pkl, "
          f"feature_columns.pkl, class_counts.json → {output_dir}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train Node 1 PyTorch MLP (8 classes, cyber-only)")
    parser.add_argument("--results-dir",    type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output-dir",     type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--init-scaler-only", action="store_true",
                        help="Fit and dump local scaler, then exit (used by FederatedClient Step 0)")
    args = parser.parse_args()

    print("=" * 65)
    print(" Node 1 Training: Class-Aware PyTorch MLP (8 classes, 11 neurons)")
    print(f" Results dir: {args.results_dir}")
    print(f" Output dir:  {args.output_dir}")
    print(f" Started:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    print("\n[Step 1] Loading cyber-only dataset...")
    master = load_cyber_only_dataset(args.results_dir)

    print("\n[Step 2] Engineering features...")
    df = engineer_features(master)

    print("\n[Step 3] Training PyTorch MLP...")
    model, scaler, le, feature_names, class_counts, acc = train(
        df, args.init_scaler_only, args.output_dir
    )

    if args.init_scaler_only:
        print("\n[Step 4] Scaler initialization complete. Exiting.")
        return

    print("\n[Step 4] Saving artifacts...")
    save_artifacts(model, scaler, le, feature_names, class_counts, args.output_dir)

    print("\n" + "=" * 65)
    print(f" Training Complete! Final accuracy: {acc * 100:.2f}%")
    print(f" Model type: Class-Aware PyTorch MLP (frozen output neurons for unseen classes)")
    print(f" Compatible with FL server (11-neuron output layer)")
    print("=" * 65)


if __name__ == "__main__":
    main()
