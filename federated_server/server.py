"""
=============================================================================
 server.py
 Federated Learning Aggregation Server (FastAPI).
=============================================================================
 Designed to be deployed on Oracle Cloud Free Tier.

 Endpoints:
   POST /submit_update : Edge Nodes post their local MLP weights (coefs, intercepts).
   GET  /global_model  : Edge Nodes fetch the latest aggregated global model.
   GET  /health        : Check server status.

 Aggregation Algorithm: FedAvg (Federated Averaging).
 Once updates from all EXPECTED_CLIENTS are received, the server computes
 the mean of the weights across all clients, updates the global model,
 and clears the pending queue.
=============================================================================
"""

import os
import json
import asyncio
from typing import Dict, List, Any
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

app = FastAPI(
    title="Federated Learning Aggregation Server",
    description="FedAvg aggregation for IIoT Edge Nodes.",
    version="1.0.0"
)

# Setup templates directory
import pathlib
templates_dir = pathlib.Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# ---------------------------------------------------------------------------
# Global State (In-Memory for now, could be backed by Redis/DB later)
# ---------------------------------------------------------------------------

# The current global model weights.
# Format: {"coefs": [list of 2D arrays], "intercepts": [list of 1D arrays]}
global_model: Dict[str, Any] = {
    "coefs": [],
    "intercepts": []
}

# The number of successful FL rounds completed.
round_number: int = 0

# Updates waiting to be aggregated for the CURRENT round.
# node_id -> {"coefs": [...], "intercepts": [...]}
pending_updates: Dict[str, Dict[str, Any]] = {}

# Lock to prevent race conditions during aggregation
aggregation_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class WeightUpdate(BaseModel):
    node_id: str
    coefs: List[List[List[float]]]       # 3D: [layer][neuron][weight]
    intercepts: List[List[float]]        # 2D: [layer][bias]


# ---------------------------------------------------------------------------
# Aggregation Logic
# ---------------------------------------------------------------------------

async def run_fedavg() -> None:
    """
    Perform Federated Averaging (FedAvg) on all pending_updates.
    Updates global_model and clears pending_updates.
    """
    global global_model, round_number, pending_updates
    
    async with aggregation_lock:
        if len(pending_updates) < EXPECTED_CLIENTS:
            return  # Safety check
            
        print(f"--- Starting FedAvg for Round {round_number + 1} ---")
        
        node_ids = list(pending_updates.keys())
        num_clients = len(node_ids)
        
        # We assume all clients have identical network architectures
        # (same number of layers and neurons per layer).
        sample_update = pending_updates[node_ids[0]]
        num_coef_layers = len(sample_update["coefs"])
        num_intercept_layers = len(sample_update["intercepts"])
        
        new_coefs = []
        new_intercepts = []
        
        # Average coefs
        for layer_idx in range(num_coef_layers):
            # Extract layer_idx from all clients and convert to numpy for easy averaging
            layer_arrays = [
                np.array(pending_updates[nid]["coefs"][layer_idx])
                for nid in node_ids
            ]
            # Mean across the client axis (axis=0)
            avg_layer = np.mean(layer_arrays, axis=0)
            new_coefs.append(avg_layer.tolist())
            
        # Average intercepts
        for layer_idx in range(num_intercept_layers):
            layer_arrays = [
                np.array(pending_updates[nid]["intercepts"][layer_idx])
                for nid in node_ids
            ]
            avg_layer = np.mean(layer_arrays, axis=0)
            new_intercepts.append(avg_layer.tolist())
            
        # Update Global State
        global_model["coefs"] = new_coefs
        global_model["intercepts"] = new_intercepts
        
        # Increment round and clear queue for the next round
        round_number += 1
        pending_updates.clear()
        
        print(f"--- FedAvg Complete. Global model is now at Round {round_number} ---")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    """Serve the Vanilla JS Dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/submit_update")
async def submit_update(update: WeightUpdate, background_tasks: BackgroundTasks):
    """
    Called by an Edge Node after it finishes training its local model.
    """
    async with aggregation_lock:
        if update.node_id in pending_updates:
            return JSONResponse(
                status_code=400,
                content={"message": f"Node {update.node_id} already submitted an update for this round."}
            )
            
        pending_updates[update.node_id] = {
            "coefs": update.coefs,
            "intercepts": update.intercepts
        }
        
        clients_ready = len(pending_updates)
        print(f"[submit_update] Received from {update.node_id}. ({clients_ready}/{EXPECTED_CLIENTS} ready)")
        
        # If we have reached the required number of clients, schedule FedAvg
        if clients_ready >= EXPECTED_CLIENTS:
            background_tasks.add_task(run_fedavg)
            msg = "Update accepted. FedAvg aggregation triggered."
        else:
            msg = "Update accepted. Waiting for other nodes."
            
    return {"message": msg, "round": round_number + 1}


@app.get("/global_model")
async def get_global_model():
    """
    Called by an Edge Node to retrieve the latest aggregated model weights.
    If no global model exists yet (Round 0), returns a 404.
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
    """Server status for monitoring."""
    return {
        "status": "healthy",
        "expected_clients": EXPECTED_CLIENTS,
        "current_round": round_number,
        "pending_updates_count": len(pending_updates)
    }

if __name__ == "__main__":
    import uvicorn
    # Bind to 0.0.0.0 so it is accessible from the internet (via Oracle Cloud VCN)
    uvicorn.run(app, host="0.0.0.0", port=8000)
