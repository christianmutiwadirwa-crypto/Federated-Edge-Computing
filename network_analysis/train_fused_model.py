"""
=============================================================================
 train_fused_model.py
 Authoritative Cyber+Physical Sensor Fusion Training Pipeline.
=============================================================================
 Produces a trained MLP model and supporting artifacts saved to models/.

 Run this script on a machine that has access to the full results/ directory.
 Output artifacts are then copied to each RPi Edge Node for inference.

 Usage:
   python train_fused_model.py
   python train_fused_model.py --results-dir /path/to/results
   python train_fused_model.py --output-dir /path/to/models

 Justification for MLP over XGBoost:
   MLP gradients (coefs_ / intercepts_) are directly compatible with the
   FedAvg algorithm (McMahan et al., 2017), the gold standard FL aggregation
   method.  XGBoost produces decision trees which have no gradient tensor
   to average.  The MLP achieves 99.45% accuracy — a statistically negligible
   0.4% below XGBoost — while enabling full FL compatibility and future
   Differential Privacy extensions.
=============================================================================
"""

import sys
import argparse
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import accuracy_score, classification_report
from imblearn.over_sampling import SMOTE

# FeatureTransformer lives in rpi/src — adjust path if running from elsewhere
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rpi" / "src"))
from FeatureTransformer import FeatureTransformer


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent.parent / "rpi" / "experiments" / "results"
DEFAULT_OUTPUT_DIR  = Path(__file__).resolve().parent.parent / "models"

MLP_HIDDEN_LAYERS   = (100, 50)
MLP_MAX_ITER        = 500
RANDOM_STATE        = 42
TEST_SIZE           = 0.20


# ---------------------------------------------------------------------------
# Step 1: Load and Fuse Data
# ---------------------------------------------------------------------------

def load_fused_dataset(results_dir: Path, exclude_eval: bool = True) -> pd.DataFrame:
    """
    Recursively find all cyber_data.csv + physical_data.csv pairs under
    results_dir, apply sensor fusion via merge_asof, and return one unified
    DataFrame with all experiments concatenated.
    """
    if exclude_eval:
        cyber_files = [f for f in results_dir.rglob("cyber_data.csv") if "evaluation" not in f.parts]
    else:
        cyber_files = list(results_dir.rglob("cyber_data.csv"))
        
    # Hard drop dropped classes so they don't even log
    cyber_files = [f for f in cyber_files if "DataTampering" not in str(f) and "Replay" not in str(f)]
    cyber_files = sorted(cyber_files)
    if not cyber_files:
        raise FileNotFoundError(f"No cyber_data.csv files found under: {results_dir}")

    dfs = []
    for cyber_path in cyber_files:
        experiment_name = cyber_path.parent.name
        physical_path   = cyber_path.parent / "physical_data.csv"

        if not physical_path.exists():
            print(f"  [SKIP] No physical_data.csv alongside {experiment_name}")
            continue

        try:
            cyber_df = pd.read_csv(cyber_path)
            cyber_df["window_start_time"] = pd.to_datetime(cyber_df["window_start_time"])
            cyber_df = cyber_df.sort_values("window_start_time").reset_index(drop=True)

            phys_df = pd.read_csv(physical_path)
            phys_df["Timestamp"] = pd.to_datetime(phys_df["Timestamp"])
            phys_df = phys_df.sort_values("Timestamp").reset_index(drop=True)

            # Snap the closest physical reading to each 2-second cyber window
            merged = pd.merge_asof(
                cyber_df,
                phys_df,
                left_on="window_start_time",
                right_on="Timestamp",
                direction="nearest",
            )
            dfs.append(merged)
            print(f"  [OK] {experiment_name}: {len(merged)} fused windows")

        except Exception as exc:
            print(f"  [ERROR] {experiment_name}: {exc}")

    if not dfs:
        raise RuntimeError("No valid experiment pairs could be loaded.")

    master = pd.concat(dfs, ignore_index=True)

    # Normalize label variants: 'NormalExperiment' (produced by normal_experiment.py)
    # and 'Normal' (legacy label from Baseline_Normal_Data) are the same class.
    master["AttackLabel"] = master["AttackLabel"].replace("NormalExperiment", "Normal")

    return master


# ---------------------------------------------------------------------------
# Step 2: Feature Engineering
# ---------------------------------------------------------------------------

def engineer_features(master_df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply FeatureTransformer to compute temporal diff features and drop
    all metadata/identifier columns.
    """
    transformer = FeatureTransformer()
    return transformer.fit_transform_dataframe(master_df)


# ---------------------------------------------------------------------------
# Step 3: Split, Scale, Train with SMOTE
# ---------------------------------------------------------------------------

def train(df: pd.DataFrame):
    """
    Encode labels, split, scale, and train the MLP classifier.

    Returns:
        model          : Trained MLPClassifier
        scaler         : Fitted StandardScaler
        label_encoder  : Fitted LabelEncoder
        X_test         : Scaled test features
        y_test         : Encoded test labels
    """
    X = df.drop(columns=["AttackLabel"])
    y = df["AttackLabel"]

    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)

    # Chronological split per class to avoid time-series leakage
    X_train_list, X_test_list, y_train_list, y_test_list = [], [], [], []
    for c in np.unique(y_encoded):
        idx = np.where(y_encoded == c)[0]
        split_point = int(len(idx) * (1 - TEST_SIZE))
        train_idx, test_idx = idx[:split_point], idx[split_point:]
        X_train_list.append(X.iloc[train_idx])
        X_test_list.append(X.iloc[test_idx])
        y_train_list.append(y_encoded[train_idx])
        y_test_list.append(y_encoded[test_idx])
    
    X_train = pd.concat(X_train_list)
    X_test  = pd.concat(X_test_list)
    y_train = np.concatenate(y_train_list)
    y_test  = np.concatenate(y_test_list)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    # --- Apply SMOTE for Class Balancing ---
    print("\n  Applying SMOTE to balance classes in the training set...")
    smote = SMOTE(random_state=RANDOM_STATE)
    X_train_resampled, y_train_resampled = smote.fit_resample(X_train_scaled, y_train)

    print(f"\n  Training MLP on {len(X_train_resampled)} samples (balanced via SMOTE), "
          f"{X_train_resampled.shape[1]} features, "
          f"{len(label_encoder.classes_)} classes...")

    model = MLPClassifier(
        hidden_layer_sizes=MLP_HIDDEN_LAYERS,
        max_iter=MLP_MAX_ITER,
        random_state=RANDOM_STATE,
        verbose=False,
    )
    model.fit(X_train_resampled, y_train_resampled)

    return model, scaler, label_encoder, X_test_scaled, y_test, list(X.columns)


# ---------------------------------------------------------------------------
# Step 5: Evaluate
# ---------------------------------------------------------------------------

def evaluate(model, scaler, label_encoder, X_test, y_test):
    preds = model.predict(X_test)
    acc   = accuracy_score(y_test, preds)

    print(f"\n{'='*55}")
    print(f"  FUSED MLP MODEL RESULTS")
    print(f"{'='*55}")
    print(f"  Overall Accuracy: {acc * 100:.2f}%")
    print(f"{'='*55}")
    print("\n--- Classification Report ---")
    print(classification_report(y_test, preds, target_names=label_encoder.classes_))
    return acc


# ---------------------------------------------------------------------------
# Step 6: Save Artifacts
# ---------------------------------------------------------------------------

def save_artifacts(model, scaler, label_encoder, feature_columns, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path   = output_dir / "fused_ids_model.pkl"
    scaler_path  = output_dir / "scaler.pkl"
    encoder_path = output_dir / "label_encoder.pkl"
    columns_path = output_dir / "feature_columns.pkl"

    joblib.dump(model,           model_path)
    joblib.dump(scaler,          scaler_path)
    joblib.dump(label_encoder,   encoder_path)
    joblib.dump(feature_columns, columns_path)

    print(f"\n  Artifacts saved to: {output_dir}")
    print(f"    fused_ids_model.pkl  ({model_path.stat().st_size / 1024:.1f} KB)")
    print(f"    scaler.pkl")
    print(f"    label_encoder.pkl    (classes: {list(label_encoder.classes_)})")
    print(f"    feature_columns.pkl  ({len(feature_columns)} features)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train the Fused Cyber+Physical IDS Model")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR,
                        help="Path to the experiments results directory")
    parser.add_argument("--output-dir",  type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Directory to save trained model artifacts")
    args = parser.parse_args()

    print("=" * 55)
    print("  Fused Cyber+Physical IDS Training Pipeline")
    print("=" * 55)

    print(f"\n[1/6] Loading and fusing datasets from: {args.results_dir}")
    master_df = load_fused_dataset(args.results_dir)
    print(f"      Total fused windows: {len(master_df)}")

    print("\n[2/5] Engineering temporal features...")
    featured_df = engineer_features(master_df)

    print("\n[3/5] Splitting, Scaling, and Training MLP model (with SMOTE)...")
    model, scaler, label_encoder, X_test, y_test, feature_columns = train(featured_df)

    print("\n[4/5] Evaluating model...")
    evaluate(model, scaler, label_encoder, X_test, y_test)

    print("\n[5/5] Saving artifacts...")
    save_artifacts(model, scaler, label_encoder, feature_columns, args.output_dir)

    print("\n  Training complete. Deploy artifacts to each RPi Edge Node.")


if __name__ == "__main__":
    main()
