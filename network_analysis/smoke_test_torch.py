import torch
import numpy as np
import sys
sys.path.insert(0, ".")
from mlp_torch import FederatedMLP, extract_weights, apply_weights, save_model, load_model, federated_loss
from pathlib import Path

print("--- Test 1: Weight round-trip ---")
m = FederatedMLP(29)
save_model(m, Path("test_round_trip.pth"))

w = extract_weights(m)
print("Coefs layer shapes:", [str(len(c))+"x"+str(len(c[0])) for c in w["coefs"]])
print("Intercept sizes   :", [len(i) for i in w["intercepts"]])

m2 = FederatedMLP(29)
apply_weights(m2, w["coefs"], w["intercepts"])

x = torch.randn(8, 29)
with torch.no_grad():
    diff = (m(x) - m2(x)).abs().max().item()
print(f"Max roundtrip error: {diff:.2e}  (target: ~0)")
assert diff < 1e-5, "ROUNDTRIP FAILED"

print("\n--- Test 2: Gradient freeze hooks ---")
m3 = FederatedMLP(29)
m3.register_class_freeze_hooks({7, 9, 10})

x2 = torch.randn(16, 29)
y2 = torch.randint(0, 8, (16,))
logits = m3(x2)
loss = torch.nn.functional.cross_entropy(logits, y2)
loss.backward()

frozen_grad = m3.output.weight.grad[:, [7, 9, 10]]
active_grad = m3.output.weight.grad[:, [0, 1, 2, 3, 4, 5, 6, 8]]
print(f"Frozen class grad max (must be 0.0) : {frozen_grad.abs().max().item():.2e}")
print(f"Active class grad max (must be >0)  : {active_grad.abs().max().item():.4f}")
assert frozen_grad.abs().max().item() < 1e-9, "FREEZE FAILED"
assert active_grad.abs().max().item() > 0, "ACTIVE GRAD FAILED"

print("\n--- Test 3: Composite federated loss ---")
student_logits  = torch.randn(16, 11)
teacher_logits  = torch.randn(16, 11)
labels          = torch.randint(0, 11, (16,))
s_params        = [torch.randn(10, 11, requires_grad=True)]
g_params        = [torch.randn(10, 11)]
loss = federated_loss(student_logits, labels, teacher_logits, s_params, g_params)
print(f"Composite loss value: {loss.item():.4f}")
assert loss.item() > 0, "LOSS FAILED"

import os
os.remove("test_round_trip.pth")

print("\nALL TESTS PASSED")
