"""
=============================================================================
 auto_federate.py
 Automated Federated Learning Runner with Per-Round Accuracy Logging.
=============================================================================
 Runs N federated rounds, and after each round evaluates both:
   - The LOCAL model  (what this node trained before FedAvg)
   - The GLOBAL model (the merged result from the FL server)
 against the evaluation dataset, and prints a live accuracy table.
=============================================================================
"""

import subprocess
import time
import sys
import json
import tempfile
import argparse
from pathlib import Path

BASE_DIR    = Path(__file__).resolve().parent
MODELS_DIR  = BASE_DIR / "models"
ARCHIVE_DIR = MODELS_DIR / "archive"
EVAL_DIR    = BASE_DIR / "rpi" / "experiments" / "results" / "evaluation"
TEST_SCRIPT = BASE_DIR / "network_analysis" / "test_fused_model.py"
FL_CLIENT   = BASE_DIR / "rpi" / "src" / "FederatedClient.py"


def evaluate_model(model_path: Path, label: str) -> float:
    """Run test_fused_model.py against the evaluation set and return accuracy."""
    if not model_path.exists():
        print(f"  [SKIP] {label}: model file not found ({model_path.name})")
        return -1.0
    if not EVAL_DIR.exists():
        print(f"  [SKIP] Evaluation dataset not found at {EVAL_DIR}")
        return -1.0

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                sys.executable, str(TEST_SCRIPT),
                "--model-path",  str(model_path),
                "--results-dir", str(EVAL_DIR),
                "--output-json", str(tmp_path),
                "--models-dir",  str(MODELS_DIR),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  [ERROR] {label} evaluation failed:\n{result.stderr[:400]}")
            return -1.0

        with open(tmp_path) as f:
            metrics = json.load(f)
        return metrics.get("accuracy", -1.0)

    except Exception as e:
        print(f"  [ERROR] {label} evaluation crashed: {e}")
        return -1.0
    finally:
        tmp_path.unlink(missing_ok=True)


def print_accuracy_table(history: list[dict]):
    """Print a live running accuracy table for all completed rounds."""
    print()
    print("=" * 65)
    print(f"  {'Round':<8} {'Local Acc':>12} {'Global Acc':>12} {'Delta':>10}")
    print("-" * 65)
    for entry in history:
        local_str  = f"{entry['local_acc']*100:.2f}%"  if entry['local_acc']  >= 0 else "N/A"
        global_str = f"{entry['global_acc']*100:.2f}%" if entry['global_acc'] >= 0 else "N/A"
        delta_str  = ""
        if entry['local_acc'] >= 0 and entry['global_acc'] >= 0:
            delta = (entry['global_acc'] - entry['local_acc']) * 100
            sign  = "+" if delta >= 0 else ""
            delta_str = f"{sign}{delta:.2f}%"
        print(f"  {entry['round']:<8} {local_str:>12} {global_str:>12} {delta_str:>10}")
    print("=" * 65)
    print()


def main():
    parser = argparse.ArgumentParser(description="Automate Federated Learning Rounds with live accuracy logging")
    parser.add_argument("--rounds", type=int, default=10, help="Number of FL rounds to run")
    parser.add_argument("--start-round", type=int, default=1, help="Round number to start from (for logging)")
    parser.add_argument("--delay",  type=int, default=5,  help="Delay in seconds between rounds")
    args = parser.parse_args()

    if not FL_CLIENT.exists():
        print(f"[!] Could not find {FL_CLIENT}")
        print("Please place this script in the root 'Federated Learning' directory.")
        sys.exit(1)

    if not EVAL_DIR.exists():
        print(f"[WARNING] Evaluation dataset not found at {EVAL_DIR}")
        print("         Accuracy reporting will be skipped — rounds will still run.")

    print(f"\n{'='*65}")
    print(f"  Automatic Federated Learning  |  {args.rounds} Rounds (Starting from R{args.start_round})")
    print(f"{'='*65}\n")

    history = []

    for i in range(args.start_round, args.start_round + args.rounds):
        print(f"\n{'='*65}")
        print(f"  STARTING FL ROUND {i}")
        print(f"{'='*65}\n")

        # Run the FL round
        result = subprocess.run([sys.executable, str(FL_CLIENT)])

        if result.returncode != 0:
            print(f"\n[!] Round {i} failed (exit code {result.returncode}). Stopping.")
            break

        # --- Evaluate local and global models ---
        print(f"\n[*] Round {i} complete. Evaluating models against evaluation set...")

        local_path  = ARCHIVE_DIR / f"fused_ids_model_local_R{i}.pth"
        global_path = ARCHIVE_DIR / f"fused_ids_model_global_R{i}.pth"

        local_acc  = evaluate_model(local_path,  f"Local  R{i}")
        global_acc = evaluate_model(global_path, f"Global R{i}")

        history.append({"round": i, "local_acc": local_acc, "global_acc": global_acc})

        local_str  = f"{local_acc*100:.2f}%"  if local_acc  >= 0 else "N/A"
        global_str = f"{global_acc*100:.2f}%" if global_acc >= 0 else "N/A"

        print(f"\n  Round {i} Results:")
        print(f"    Local Model  Accuracy: {local_str}")
        print(f"    Global Model Accuracy: {global_str}")

        # Print the running table
        print_accuracy_table(history)

        # Save CSV log after each round
        log_path = ARCHIVE_DIR / "accuracy_log.csv"
        write_header = not log_path.exists()
        with open(log_path, "a") as f:
            if write_header:
                f.write("round,local_acc,global_acc\n")
            f.write(f"{i},{local_acc:.4f},{global_acc:.4f}\n")

        if i < args.rounds:
            print(f"[*] Waiting {args.delay}s before next round...\n")
            time.sleep(args.delay)

    # Final summary
    print(f"\n{'='*65}")
    print("  FINAL ACCURACY SUMMARY")
    print_accuracy_table(history)
    print(f"  CSV log saved to: {ARCHIVE_DIR / 'accuracy_log.csv'}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
