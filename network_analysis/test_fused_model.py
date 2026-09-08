"""
=============================================================================
 test_fused_model.py
 Evaluate a trained MLP (PyTorch .pth) against a specific dataset.
=============================================================================
 Outputs the metrics as a JSON file for the FederatedClient to upload.
=============================================================================
"""

import sys
import argparse
import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import accuracy_score

# FeatureTransformer and mlp_torch live in their respective directories
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rpi" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from FeatureTransformer import FeatureTransformer
from train_fused_model import load_fused_dataset, engineer_features
from mlp_torch import load_model

import torch


def test_model(model_path: Path, results_dir: Path, output_json: Path, models_dir: Path):
    print(f"[*] Testing model: {model_path.name} on dataset: {results_dir.name}")

    # Load artifacts
    try:
        model   = load_model(model_path)
        model.eval()
        scaler          = joblib.load(models_dir / "scaler.pkl")
        label_encoder   = joblib.load(models_dir / "label_encoder.pkl")
        feature_columns = joblib.load(models_dir / "feature_columns.pkl")
    except Exception as e:
        print(f"[!] Failed to load model artifacts: {e}")
        sys.exit(1)

    # Load and prepare data
    try:
        master_df   = load_fused_dataset(results_dir)
        featured_df = engineer_features(master_df)
    except Exception as e:
        print(f"[!] Failed to load dataset: {e}")
        with open(output_json, "w") as f:
            json.dump({"accuracy": 0.0, "samples": 0}, f)
        sys.exit(0)

    X_raw = featured_df.drop(columns=["AttackLabel"])
    y_raw = featured_df["AttackLabel"]

    # Reorder columns to match training exactly
    for col in feature_columns:
        if col not in X_raw.columns:
            X_raw[col] = 0.0
    X = X_raw[feature_columns]

    # Filter out unknown labels that weren't in training
    known_classes = set(label_encoder.classes_)
    valid_mask = y_raw.isin(known_classes)
    X     = X[valid_mask]
    y_raw = y_raw[valid_mask]

    if len(X) == 0:
        print("[!] No valid samples to test.")
        with open(output_json, "w") as f:
            json.dump({"accuracy": 0.0, "samples": 0}, f)
        sys.exit(0)

    y_encoded = label_encoder.transform(y_raw)
    X_scaled  = scaler.transform(X)
    # Sanitize NaN/inf from zero-variance features in Global Scaler
    X_scaled  = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)

    # Inference with PyTorch
    with torch.no_grad():
        X_tensor = torch.tensor(X_scaled, dtype=torch.float32)
        logits   = model(X_tensor)
        preds    = logits.argmax(dim=1).numpy()

    acc = accuracy_score(y_encoded, preds)

    metrics = {"accuracy": acc, "samples": len(X)}
    with open(output_json, "w") as f:
        json.dump(metrics, f)

    print(f"[*] Accuracy: {acc * 100:.2f}% ({len(X)} samples)")
    print(f"[*] Saved metrics to {output_json}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path",  type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, default=Path("metrics.json"))
    parser.add_argument("--models-dir",  type=Path, required=True)

    args = parser.parse_args()
    test_model(args.model_path, args.results_dir, args.output_json, args.models_dir)
