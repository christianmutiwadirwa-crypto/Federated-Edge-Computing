import sys
import joblib
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rpi" / "src"))
from FeatureTransformer import FeatureTransformer
from train_node1_8classes_torch import GLOBAL_CLASSES
from mlp_torch import load_model

def load_cyber_only_dataset(results_dir: Path) -> pd.DataFrame:
    cyber_files = sorted(results_dir.rglob("cyber_data.csv"))
    if not cyber_files:
        raise FileNotFoundError(f"No cyber_data.csv files found under: {results_dir}")

    dfs = []
    for cyber_path in cyber_files:
        try:
            df = pd.read_csv(cyber_path)
            df["window_start_time"] = pd.to_datetime(df["window_start_time"])
            df = df.sort_values("window_start_time").reset_index(drop=True)
            dfs.append(df)
        except Exception as exc:
            pass

    master = pd.concat(dfs, ignore_index=True)
    master["AttackLabel"] = master["AttackLabel"].replace("NormalExperiment", "Normal")
    
    # Noise cleaning
    clean_masks = [master["AttackLabel"] == "Normal"]
    other_attacks = master["AttackLabel"].isin([
        "DelayExperiment", "ConnectionResetExperiment", 
        "DuplicatePacketExperiment", "FloodingExperiment", 
        "DeviceSpoofExperiment", "PacketLossExperiment",
        "PacketInjectionExperiment", "SlowDoSExperiment"
    ])
    clean_masks.append(other_attacks & (master["total_packets"] > 2))
    final_mask = pd.concat(clean_masks, axis=1).any(axis=1)
    master = master[final_mask].reset_index(drop=True)
    
    # Filter to the 9 classes (exclude DataTampering and Replay)
    allowed = [c for c in GLOBAL_CLASSES.keys() if c not in ("DataTamperingExperiment", "ReplayExperiment")]
    master = master[master["AttackLabel"].isin(allowed)].reset_index(drop=True)
    return master

def main():
    base_dir = Path(__file__).resolve().parent.parent
    eval_dir = base_dir / "rpi" / "experiments" / "results" / "evaluation"
    models_dir = base_dir / "models"
    
    print(f"Loading holdout dataset from {eval_dir}...")
    df = load_cyber_only_dataset(eval_dir)
    print(f"Loaded {len(df)} samples across {df['AttackLabel'].nunique()} classes.")
    
    transformer = FeatureTransformer()
    featured_df = transformer.fit_transform_dataframe(df)
    
    X_raw = featured_df.drop(columns=["AttackLabel"])
    y_raw = featured_df["AttackLabel"]
    
    print(f"Loading artifacts from {models_dir}...")
    scaler = joblib.load(models_dir / "scaler.pkl")
    label_encoder = joblib.load(models_dir / "label_encoder.pkl")
    feature_columns = joblib.load(models_dir / "feature_columns.pkl")
    
    # Align features
    for col in feature_columns:
        if col not in X_raw.columns:
            X_raw[col] = 0.0
    X = X_raw[feature_columns]
    
    y_encoded = label_encoder.transform(y_raw)
    X_scaled = scaler.transform(X)
    X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
    
    print(f"Loading PyTorch model...")
    model = load_model(models_dir / "fused_ids_model.pth")
    model.eval()
    
    with torch.no_grad():
        X_tensor = torch.tensor(X_scaled, dtype=torch.float32)
        logits = model(X_tensor)
        preds = logits.argmax(dim=1).numpy()
    
    acc = accuracy_score(y_encoded, preds)
    print(f"\nHoldout Set Accuracy: {acc * 100:.2f}%")
    print("\nClassification Report:")
    print(classification_report(y_encoded, preds, target_names=label_encoder.inverse_transform(np.unique(y_encoded))))
    
    print("Confusion Matrix:")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    labels = label_encoder.inverse_transform(np.unique(y_encoded))
    cm = pd.DataFrame(confusion_matrix(y_encoded, preds), index=labels, columns=labels)
    print(cm)

if __name__ == "__main__":
    main()
