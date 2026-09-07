"""
=============================================================================
 server.py
 Federated Learning Aggregation Server (FastAPI).
=============================================================================
 Designed to be deployed on Oracle Cloud Free Tier / Render.

 System Architecture:
   ESP32 Nodes (ADXL345 accelerometer, 500 Hz, 2s windows)
     └─▶ Raspberry Pi Edge Nodes (TCP, feature extraction, MLP + IsoForest)
           └─▶ This Server (HTTP, FedAvg aggregation of MLP weights)

 Edge Node Hardware:
   - Sensor:       ADXL345 (SPI, 500 Hz, 3-axis vibration)
   - Processor:    Raspberry Pi (Python, sklearn MLP, 11-class IDS)
   - Protocol:     Custom binary TCP (magic=0xABCD, ACK=0x06)

 Endpoints:
   POST /submit_update : Edge Nodes post their local MLP weights (coefs, intercepts).
   GET  /global_model  : Edge Nodes fetch the latest aggregated global model.
   GET  /health        : Check server status (basic).
   GET  /status        : Detailed dashboard status (nodes, rounds, history).
   GET  /             : Rich HTML dashboard.

 Aggregation Algorithm: FedAvg (Federated Averaging).
 Once updates from all EXPECTED_CLIENTS are received, the server computes
 the mean of the weights across all clients, updates the global model,
 and clears the pending queue.
=============================================================================
"""

import os
import json
import asyncio
import pathlib
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import numpy as np

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Number of expected Edge Nodes. FedAvg waits until this many updates
# are received before running the aggregation.
EXPECTED_CLIENTS = int(os.environ.get("FL_EXPECTED_CLIENTS", 2))

# Known node identities (used for display in the dashboard)
# Map of node_id -> human-readable label
NODE_LABELS: Dict[str, str] = {
    "edge_node_1": "Node 1 · Raspberry Pi",
    "edge_node_2": "Node 2 · Raspberry Pi",
}

app = FastAPI(
    title="Federated Learning Aggregation Server",
    description="FedAvg aggregation for IIoT Edge Nodes (Predictive Maintenance).",
    version="2.0.0"
)

# Setup templates directory
templates_dir = pathlib.Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))


# ---------------------------------------------------------------------------
# Global State
# ---------------------------------------------------------------------------

# The current global model weights.
global_model: Dict[str, Any] = {
    "coefs": [],
    "intercepts": []
}

# The number of successful FL rounds completed.
round_number: int = 0

# Updates waiting to be aggregated for the CURRENT round.
# node_id -> {coefs, intercepts, submitted_at, architecture_summary}
pending_updates: Dict[str, Dict[str, Any]] = {}

# Per-round history (last N rounds kept in memory)
round_history: List[Dict[str, Any]] = []
MAX_HISTORY = 20

# History of global model validation accuracies submitted by nodes
validation_history: List[Dict[str, Any]] = []

# Per-node metadata tracked across rounds
node_registry: Dict[str, Dict[str, Any]] = {}

# Server start time
server_start_time: str = datetime.now(timezone.utc).isoformat()

# Lock to prevent race conditions during aggregation
aggregation_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class WeightUpdate(BaseModel):
    node_id: str
    coefs: List[List[List[float]]]       # 3D: [layer][neuron][weight]
    intercepts: List[List[float]]        # 2D: [layer][bias]
    # Optional metadata from edge node
    local_accuracy: Optional[float] = None   # 0.0–1.0 if node reports it
    training_samples: Optional[int] = None   # samples used for local training
    class_counts: Optional[List[int]] = None # samples per class for weighted aggregation


class ValidationUpdate(BaseModel):
    node_id: str
    round: int
    accuracy: float
    samples: int


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _describe_architecture(coefs: List, intercepts: List) -> str:
    """Return a human-readable MLP architecture string, e.g. '18→64→64→11'."""
    if not coefs:
        return "N/A"
    input_dim = len(coefs[0][0])
    layers = [input_dim] + [len(layer) for layer in intercepts]
    return "→".join(str(l) for l in layers)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Aggregation Logic
# ---------------------------------------------------------------------------

async def run_fedavg() -> None:
    """
    Perform Federated Averaging (FedAvg) on all pending_updates.
    Updates global_model and clears pending_updates.
    """
    global global_model, round_number, pending_updates, round_history

    async with aggregation_lock:
        if len(pending_updates) < EXPECTED_CLIENTS:
            return  # Safety check

        target_round = round_number + 1
        print(f"--- Starting FedAvg for Round {target_round} ---")

        node_ids = list(pending_updates.keys())
        num_clients = len(node_ids)

        sample_update = pending_updates[node_ids[0]]
        num_coef_layers = len(sample_update["coefs"])
        num_intercept_layers = len(sample_update["intercepts"])

        new_coefs = []
        new_intercepts = []

        # Average coefs
        for layer_idx in range(num_coef_layers):
            layer_arrays = [
                np.array(pending_updates[nid]["coefs"][layer_idx])
                for nid in node_ids
            ]
            is_output = (layer_idx == num_coef_layers - 1)
            has_counts = all(pending_updates[nid].get("class_counts") is not None for nid in node_ids)

            if is_output and has_counts:
                # Class-frequency weighting for the output layer
                n_hidden, n_classes = layer_arrays[0].shape
                avg_layer = np.zeros((n_hidden, n_classes))
                counts = [pending_updates[nid]["class_counts"] for nid in node_ids]

                for c in range(n_classes):
                    total_c = sum(node_counts[c] for node_counts in counts)
                    if total_c > 0:
                        for i, nid in enumerate(node_ids):
                            weight = counts[i][c] / total_c
                            avg_layer[:, c] += layer_arrays[i][:, c] * weight
                    else:
                        for i, nid in enumerate(node_ids):
                            avg_layer[:, c] += layer_arrays[i][:, c] / num_clients
            else:
                # Standard average for hidden layers
                avg_layer = np.mean(layer_arrays, axis=0)
                
            new_coefs.append(avg_layer.tolist())

        # Average intercepts
        for layer_idx in range(num_intercept_layers):
            layer_arrays = [
                np.array(pending_updates[nid]["intercepts"][layer_idx])
                for nid in node_ids
            ]
            is_output = (layer_idx == num_intercept_layers - 1)
            has_counts = all(pending_updates[nid].get("class_counts") is not None for nid in node_ids)

            if is_output and has_counts:
                # Class-frequency weighting for the output biases
                n_classes = layer_arrays[0].shape[0]
                avg_layer = np.zeros(n_classes)
                counts = [pending_updates[nid]["class_counts"] for nid in node_ids]

                for c in range(n_classes):
                    total_c = sum(node_counts[c] for node_counts in counts)
                    if total_c > 0:
                        for i, nid in enumerate(node_ids):
                            weight = counts[i][c] / total_c
                            avg_layer[c] += layer_arrays[i][c] * weight
                    else:
                        for i, nid in enumerate(node_ids):
                            avg_layer[c] += layer_arrays[i][c] / num_clients
            else:
                avg_layer = np.mean(layer_arrays, axis=0)
                
            new_intercepts.append(avg_layer.tolist())

        # Compute aggregation metadata
        architecture = _describe_architecture(new_coefs, new_intercepts)
        weight_params = sum(
            np.prod(np.array(c).shape) for c in new_coefs
        ) + sum(len(b) for b in new_intercepts)

        avg_accuracy = None
        acc_values = [
            pending_updates[nid].get("local_accuracy")
            for nid in node_ids
            if pending_updates[nid].get("local_accuracy") is not None
        ]
        if acc_values:
            avg_accuracy = round(float(np.mean(acc_values)), 4)

        total_samples = sum(
            pending_updates[nid].get("training_samples") or 0
            for nid in node_ids
        )

        # Update Global State
        global_model["coefs"] = new_coefs
        global_model["intercepts"] = new_intercepts

        completed_at = _now_iso()
        round_number += 1

        # Record history
        round_record = {
            "round": round_number,
            "completed_at": completed_at,
            "participating_nodes": node_ids,
            "num_clients": num_clients,
            "architecture": architecture,
            "weight_params": int(weight_params),
            "avg_local_accuracy": avg_accuracy,
            "total_training_samples": total_samples if total_samples > 0 else None,
        }
        round_history.append(round_record)
        if len(round_history) > MAX_HISTORY:
            round_history.pop(0)

        # Update node registry with last-seen round
        for nid in node_ids:
            if nid in node_registry:
                node_registry[nid]["last_round"] = round_number
                node_registry[nid]["last_update_at"] = completed_at
                node_registry[nid]["rounds_participated"] = \
                    node_registry[nid].get("rounds_participated", 0) + 1

        pending_updates.clear()

        print(f"--- FedAvg Complete. Global model at Round {round_number} "
              f"| arch={architecture} | params={weight_params:,} ---")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    """Serve the rich HTML dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/submit_update")
async def submit_update(update: WeightUpdate, background_tasks: BackgroundTasks):
    """
    Called by an Edge Node after it finishes local training.
    Accepts MLP weights (coefs + intercepts) and optional metadata.
    """
    async with aggregation_lock:
        if update.node_id in pending_updates:
            return JSONResponse(
                status_code=400,
                content={
                    "message": f"Node '{update.node_id}' already submitted for this round.",
                    "round": round_number + 1
                }
            )

        architecture = _describe_architecture(update.coefs, update.intercepts)
        submitted_at = _now_iso()

        pending_updates[update.node_id] = {
            "coefs": update.coefs,
            "intercepts": update.intercepts,
            "submitted_at": submitted_at,
            "architecture": architecture,
            "local_accuracy": update.local_accuracy,
            "training_samples": update.training_samples,
            "class_counts": update.class_counts,
        }

        # Update node registry
        if update.node_id not in node_registry:
            node_registry[update.node_id] = {
                "node_id": update.node_id,
                "label": NODE_LABELS.get(update.node_id, update.node_id),
                "first_seen": submitted_at,
                "last_update_at": submitted_at,
                "last_round": None,
                "rounds_participated": 0,
                "architecture": architecture,
            }
        else:
            node_registry[update.node_id]["last_update_at"] = submitted_at
            node_registry[update.node_id]["architecture"] = architecture

        clients_ready = len(pending_updates)
        print(f"[submit_update] Received from '{update.node_id}' "
              f"(arch={architecture}). ({clients_ready}/{EXPECTED_CLIENTS} ready)")

        if clients_ready >= EXPECTED_CLIENTS:
            background_tasks.add_task(run_fedavg)
            msg = "Update accepted. FedAvg aggregation triggered."
        else:
            msg = f"Update accepted. Waiting for {EXPECTED_CLIENTS - clients_ready} more node(s)."

    return {
        "message": msg,
        "round": round_number + 1,
        "nodes_ready": clients_ready,
        "nodes_expected": EXPECTED_CLIENTS
    }


@app.post("/submit_validation")
async def submit_validation(validation: ValidationUpdate):
    """
    Called by an Edge Node after it evaluates the incoming global model
    on its local holdout dataset. Used for convergence dashboarding.
    """
    record = {
        "node_id": validation.node_id,
        "round": validation.round,
        "accuracy": validation.accuracy,
        "samples": validation.samples,
        "submitted_at": _now_iso()
    }
    validation_history.append(record)
    
    # Keep it bounded (e.g. max 100 records)
    if len(validation_history) > 100:
        validation_history.pop(0)
        
    return {"message": "Validation metrics recorded."}

@app.get("/global_model")
async def get_global_model():
    """
    Called by an Edge Node to retrieve the latest aggregated model weights.
    Returns 404 if no global model exists yet (Round 0).
    """
    async with aggregation_lock:
        if not global_model["coefs"]:
            raise HTTPException(status_code=404, detail="No global model generated yet.")

        return {
            "round": round_number,
            "weights": global_model
        }


@app.get("/health")
async def health_check():
    """Basic health check (backwards-compatible with edge nodes)."""
    return {
        "status": "healthy",
        "expected_clients": EXPECTED_CLIENTS,
        "current_round": round_number,
        "pending_updates_count": len(pending_updates)
    }


@app.get("/status")
async def detailed_status():
    """
    Rich status endpoint for the dashboard.
    Returns full server state: round info, pending nodes, history, node registry.
    """
    # Build pending node list with architecture and timing
    pending_node_list = []
    for nid, info in pending_updates.items():
        pending_node_list.append({
            "node_id": nid,
            "label": NODE_LABELS.get(nid, nid),
            "submitted_at": info.get("submitted_at"),
            "architecture": info.get("architecture"),
            "local_accuracy": info.get("local_accuracy"),
            "training_samples": info.get("training_samples"),
        })

    # Global model metadata
    global_meta = None
    if global_model["coefs"]:
        architecture = _describe_architecture(global_model["coefs"], global_model["intercepts"])
        weight_params = sum(
            np.prod(np.array(c).shape) for c in global_model["coefs"]
        ) + sum(len(b) for b in global_model["intercepts"])
        global_meta = {
            "architecture": architecture,
            "num_layers": len(global_model["coefs"]) + 1,
            "weight_params": int(weight_params),
        }

    return {
        "server": {
            "status": "healthy",
            "start_time": server_start_time,
            "expected_clients": EXPECTED_CLIENTS,
            "algorithm": "FedAvg",
            "model_type": "MLP Classifier (sklearn)",
            "task": "11-class Cyber Intrusion Detection",
            "deployment": "Oracle Cloud / Render",
        },
        "current_round": round_number,
        "next_round": round_number + 1,
        "pending_updates_count": len(pending_updates),
        "pending_nodes": pending_node_list,
        "global_model": global_meta,
        "node_registry": list(node_registry.values()),
        "round_history": list(reversed(round_history)),  # newest first
        "validation_history": list(reversed(validation_history)),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
