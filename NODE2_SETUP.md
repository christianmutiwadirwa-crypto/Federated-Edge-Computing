# Node 2 Federated Learning Setup Guide

Welcome to the Edge Node Federation! By joining this network, your Edge Node will train a local PyTorch Neural Network and Isolation Forest on your unique cyber-attacks, and securely contribute that knowledge to the Global Model via our Render Cloud Server.

## Prerequisites
1. A Raspberry Pi or local machine running Python 3.9+.
2. The `rpi/` directory and its `requirements.txt` installed.

## Step 1: Configure Your Node
Open your terminal and set your Node ID environment variable:

**Windows (PowerShell):**
```powershell
$env:NODE_ID="edge_node_2"
```

**Linux/Mac (Bash):**
```bash
export NODE_ID="edge_node_2"
```

*Note: As Node 2, you are strictly responsible for becoming the network's expert on `FloodingExperiment` and `DeviceSpoofHardExperiment`. You will also train on shared classes like `SlowDoS` and `DataTamperingCRCForged`.*

## Step 2: Physical Baseline Profiling (Isolation Forest)
Before training the Cyber PyTorch model, your node must learn what "Normal" physical vibration looks like for your specific hardware.
Run the shaker collection script to capture 45 minutes of baseline telemetry:
```bash
python rpi/experiments/collect_shaker_data.py
```
Once complete, train your local Isolation Forest on this data:
```bash
python network_analysis/train_iso_forest.py
```

## Step 3: Collect Cyber Training & Evaluation Data
Next, you must simulate the cyber attacks to generate your training dataset. This requires running both batches.

**Collect Training Batch 1 & 2:**
```bash
python rpi/experiments/collect_train_data.py --batch 1
python rpi/experiments/collect_train_data.py --batch 2
```

**Collect Evaluation Holdout Data:**
```bash
python rpi/experiments/collect_eval_data.py
```
*All raw CSV and PCAP data is saved to `rpi/experiments/results/`. This raw data will NEVER leave your machine.*

## Step 4: Trigger the Federation Round
Once your physical and cyber datasets are collected and your Isolation Forest is trained, you are ready to join the PyTorch network:

```bash
# Windows (PowerShell): Run 10 rounds of federation
1..10 | ForEach-Object { python rpi/src/FederatedClient.py }

# Linux/Mac (Bash): Run 10 rounds of federation
for i in {1..10}; do python rpi/src/FederatedClient.py; done
```

**What this script does automatically:**
1. **Local Architecture Initialization:** It triggers `train_federated_node.py`. Even though your node only collected data for 6 specific attack classes, this script forces your PyTorch Neural Network to instantiate with **9 output neurons**.
2. **Local Training:** It trains the weights for your 6 classes, leaving the remaining 3 output neurons completely frozen/zeroed out so they don't corrupt during training.
3. **Federation Upload:** It connects to `https://federated-edge-computing.onrender.com` via REST API and uploads your model's gradients.
4. **Polling:** It waits until `edge_node_1` also uploads its weights.
5. **Global Fusion:** It downloads the mathematically averaged Global Model (where Node 1 has populated the knowledge for the remaining 3 neurons).
6. **Hot-Reload:** It overwrites your local model and reboots your `InferenceEngine` with the new global brain.

You are now fully synchronized and capable of detecting attacks that only Node 1 has seen!
