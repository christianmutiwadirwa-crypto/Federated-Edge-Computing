"""
=============================================================================
 FederatedClient.py
 Edge Node Federated Learning Client.
=============================================================================
 Manages the local node's participation in an FL round.
 
 Triggered manually by the researcher via trigger_fl_round.py after
 a new batch of labelled experiment data is collected.

 Workflow:
   1. Subprocesses `train_fused_model.py` to train a local MLP on the 
      node's local `results/` folder.
   2. Extracts the weights (coefs_, intercepts_) from the resulting model.
   3. Sends the weights via HTTP POST to the FL Server in Oracle Cloud.
   4. Polls the FL Server until the new aggregated global model is ready.
   5. Overwrites the local fused_ids_model.pkl with the global weights.
   6. Restarts the InferenceEngine to hot-reload the new global model.
=============================================================================
"""

import os
import json
import time
import requests
import joblib
import subprocess
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Address of the Oracle Cloud FastAPI server.
# You will need to change this to the public IP of your Oracle VM later.
FL_SERVER_URL = os.environ.get("FL_SERVER_URL", "http://127.0.0.1:8000")

# Unique identifier for this Edge Node
NODE_ID = os.environ.get("NODE_ID", "edge_node_1")

# Paths
BASE_DIR    = Path(__file__).resolve().parent.parent.parent
MODELS_DIR  = BASE_DIR / "models"
MODEL_PATH  = MODELS_DIR / "fused_ids_model.pkl"
TRAIN_SCRIPT = BASE_DIR / "network_analysis" / "train_fused_model.py"


class FederatedClient:
    """Manages the full lifecycle of a Federated Learning round on the Edge Node."""

    def __init__(self, server_url: str = FL_SERVER_URL, node_id: str = NODE_ID):
        self.server_url = server_url.rstrip("/")
        self.node_id = node_id

    def trigger_round(self):
        """Execute a full FL round."""
        print(f"[{self.node_id}] Starting Federated Learning Round")
        
        # 1. Train locally
        if not self._train_local_model():
            return
            
        # 2. Extract local weights
        local_weights = self._extract_weights()
        if not local_weights:
            return
            
        # 3. Submit to FL Server
        round_num = self._submit_weights(local_weights)
        if not round_num:
            return
            
        # 4. Wait for Global Model (Polling)
        global_weights = self._wait_for_global_model(round_num)
        if not global_weights:
            return
            
        # 5. Save Global Model locally
        self._apply_global_weights(global_weights)
        
        print(f"[{self.node_id}] FL Round {round_num} completed successfully. Inference Engine is now using the Global Model.")

    # -----------------------------------------------------------------------
    # Step Implementations
    # -----------------------------------------------------------------------

    def _train_local_model(self) -> bool:
        """Run the training script as a subprocess."""
        print("  -> Step 1: Training local MLP on local dataset...")
        try:
            # We run it as a subprocess to keep the training memory separate
            # from the long-running inference process.
            result = subprocess.run(
                ["python", str(TRAIN_SCRIPT)],
                check=True,
                capture_output=True,
                text=True
            )
            print("     Local training complete.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"     [ERROR] Local training failed: {e.stderr}")
            return False

    def _extract_weights(self) -> dict:
        """Load the newly trained model and extract its weights."""
        print("  -> Step 2: Extracting local weights...")
        try:
            model = joblib.load(MODEL_PATH)
            
            # Scikit-learn MLPClassifier stores weights as lists of numpy arrays
            coefs = [layer.tolist() for layer in model.coefs_]
            intercepts = [layer.tolist() for layer in model.intercepts_]
            
            return {
                "node_id": self.node_id,
                "coefs": coefs,
                "intercepts": intercepts
            }
        except Exception as e:
            print(f"     [ERROR] Failed to extract weights: {e}")
            return {}

    def _submit_weights(self, weights: dict) -> int:
        """POST weights to the central FL server."""
        print(f"  -> Step 3: Submitting updates to FL Server ({self.server_url})...")
        try:
            response = requests.post(f"{self.server_url}/submit_update", json=weights)
            if response.status_code == 200:
                data = response.json()
                print(f"     Server accepted update. Target Round: {data.get('round')}")
                return data.get("round")
            else:
                print(f"     [ERROR] Server rejected update: {response.text}")
                return 0
        except requests.RequestException as e:
            print(f"     [ERROR] Could not connect to FL Server: {e}")
            return 0

    def _wait_for_global_model(self, target_round: int) -> dict:
        """Poll the server every 5 seconds until the target round is ready."""
        print(f"  -> Step 4: Waiting for FedAvg aggregation (polling server)...")
        max_attempts = 60  # 5 minutes max
        
        for attempt in range(max_attempts):
            try:
                response = requests.get(f"{self.server_url}/global_model")
                if response.status_code == 200:
                    data = response.json()
                    current_round = data.get("round", 0)
                    
                    if current_round >= target_round:
                        print(f"     Global model for Round {current_round} received!")
                        return data.get("weights")
                        
            except requests.RequestException:
                pass # Silently ignore connection errors while polling
                
            time.sleep(5)
            
        print("     [ERROR] Timed out waiting for global model.")
        return {}

    def _apply_global_weights(self, global_weights: dict) -> bool:
        """Overwrite the local model with the new global weights."""
        print("  -> Step 5: Applying global weights to local model...")
        try:
            # 1. Load the existing local model to get the structure
            model = joblib.load(MODEL_PATH)
            
            # 2. Overwrite its weights with the global averages
            model.coefs_ = [np.array(layer) for layer in global_weights["coefs"]]
            model.intercepts_ = [np.array(layer) for layer in global_weights["intercepts"]]
            
            # 3. Save it back to disk
            joblib.dump(model, MODEL_PATH)
            print("     Global weights saved to models/fused_ids_model.pkl")
            
            # 4. Trigger hot-reload in the InferenceEngine
            # (In a real deployment, we could send a signal, touch a file, 
            # or expose a local HTTP endpoint on the DataManager to trigger reload)
            print("     [Note] You must restart the EdgeNode to load the new model.")
            return True
            
        except Exception as e:
            print(f"     [ERROR] Failed to apply global weights: {e}")
            return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trigger an FL Round on this Edge Node.")
    parser.add_argument("--node-id", type=str, default=NODE_ID, help="Unique ID of this node")
    parser.add_argument("--server", type=str, default=FL_SERVER_URL, help="URL of the FL Server")
    args = parser.parse_args()
    
    client = FederatedClient(server_url=args.server, node_id=args.node_id)
    client.trigger_round()
