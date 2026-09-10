import subprocess
import time
import os
import sys

print("Starting Local FL Server...")
server_proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "federated_server.server:app", "--port", "8000"],
    stdout=open("server.log", "w", encoding="utf-8"),
    stderr=subprocess.STDOUT
)
time.sleep(4)

print("Starting Node 1 (Rounds=2)...")
env1 = os.environ.copy()
env1["NODE_ID"] = "edge_node_1"
env1["FL_SERVER_URL"] = "http://localhost:8000"
node1_proc = subprocess.Popen(
    [sys.executable, "auto_federate.py", "--rounds", "2"],
    env=env1,
    stdout=open("node1.log", "w", encoding="utf-8"),
    stderr=subprocess.STDOUT
)

print("Starting Node 2 (Rounds=2)...")
env2 = os.environ.copy()
env2["NODE_ID"] = "edge_node_2"
env2["FL_SERVER_URL"] = "http://localhost:8000"
node2_proc = subprocess.Popen(
    [sys.executable, "auto_federate.py", "--rounds", "2"],
    env=env2,
    stdout=open("node2.log", "w", encoding="utf-8"),
    stderr=subprocess.STDOUT
)

print("Waiting for both nodes to complete...")
node1_proc.wait()
node2_proc.wait()

server_proc.terminate()
print("Simulation complete! Check node1.log and node2.log.")
