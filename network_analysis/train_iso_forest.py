"""
=============================================================================
 train_iso_forest.py
 Train an Isolation Forest on Normal Physical Data.
=============================================================================
"""

import sys
import argparse
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent.parent / "rpi" / "experiments" / "results"
DEFAULT_OUTPUT_DIR  = Path(__file__).resolve().parent.parent / "models"
RANDOM_STATE        = 42
CONTAMINATION       = 0.01  # Expected anomaly rate in training data (set low for normal data)

PHYSICAL_METADATA_COLS = ["Timestamp", "Node ID", "Label"]

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def load_normal_physical_data(results_dir: Path) -> pd.DataFrame:
    """
    Load physical_data.csv from all 'Normal' or 'NormalExperiment' results directories.
    """
    dfs = []
    
    # Iterate through all subdirectories in results
    if not results_dir.exists():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")
        
    for exp_dir in results_dir.iterdir():
        if exp_dir.is_dir() and (exp_dir.name.startswith("Normal_") or exp_dir.name.startswith("NormalExperiment_")):
            phys_csv = exp_dir / "physical_data.csv"
            if phys_csv.exists():
                try:
                    df = pd.read_csv(phys_csv)
                    dfs.append(df)
                    print(f"  [OK] Loaded {len(df)} physical samples from {exp_dir.name}")
                except Exception as e:
                    print(f"  [ERROR] Could not read {phys_csv}: {e}")
                    
    if not dfs:
        raise ValueError("No normal physical data found.")
        
    master_df = pd.concat(dfs, ignore_index=True)
    return master_df

def train_isolation_forest(df: pd.DataFrame):
    """
    Extract features, scale, and fit the Isolation Forest.
    """
    # Drop metadata columns to get pure features
    cols_to_drop = [c for c in PHYSICAL_METADATA_COLS if c in df.columns]
    X = df.drop(columns=cols_to_drop)
    
    # Ensure all columns are numeric, drop any rows with NaN
    X = X.dropna()
    feature_columns = list(X.columns)
    
    print(f"\n  Training Isolation Forest on {len(X)} normal physical samples, "
          f"{len(feature_columns)} features...")
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Fit Isolation Forest
    model = IsolationForest(
        n_estimators=100,
        max_samples='auto',
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1
    )
    model.fit(X_scaled)
    
    return model, scaler, feature_columns

def save_artifacts(model, scaler, feature_columns, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    
    model_path   = output_dir / "iso_forest_model.pkl"
    scaler_path  = output_dir / "iso_scaler.pkl"
    columns_path = output_dir / "iso_physical_columns.pkl"
    
    joblib.dump(model,           model_path)
    joblib.dump(scaler,          scaler_path)
    joblib.dump(feature_columns, columns_path)
    
    print(f"\n  Artifacts saved to: {output_dir}")
    print(f"    iso_forest_model.pkl")
    print(f"    iso_scaler.pkl")
    print(f"    iso_physical_columns.pkl ({len(feature_columns)} features)")

def main():
    parser = argparse.ArgumentParser(description="Train Isolation Forest on Normal Physical Data")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR,
                        help="Path to the experiments results directory")
    parser.add_argument("--output-dir",  type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Directory to save trained model artifacts")
    args = parser.parse_args()

    print("=" * 55)
    print("  Isolation Forest Training Pipeline (Physical Only)")
    print("=" * 55)

    print(f"\n[1/3] Loading normal physical data from: {args.results_dir}")
    master_df = load_normal_physical_data(args.results_dir)

    print("\n[2/3] Training model...")
    model, scaler, feature_columns = train_isolation_forest(master_df)

    print("\n[3/3] Saving artifacts...")
    save_artifacts(model, scaler, feature_columns, args.output_dir)

    print("\n  Training complete.")

if __name__ == "__main__":
    main()
