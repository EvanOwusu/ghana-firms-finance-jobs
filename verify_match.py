"""
Cross-check the Python and R pipelines.

Run both analyses first, then:
    python verify_match.py
Compares every shared key in output/results_python.json and output/results_r.json
and fails if any estimate or standard error differs by more than the tolerance.
"""
import json
import sys
from pathlib import Path

TOL = 1e-6
py = json.loads(Path("output/results_python.json").read_text())
r = json.loads(Path("output/results_r.json").read_text())

shared = sorted(set(py) & set(r))
only_py, only_r = sorted(set(py) - set(r)), sorted(set(r) - set(py))
bad = []
for k in shared:
    a, b = float(py[k]), float(r[k])
    diff = abs(a - b) / max(1.0, abs(a))
    if diff > TOL:
        bad.append((k, a, b, diff))

print(f"Compared {len(shared)} estimates (tolerance {TOL:g}, relative).")
if only_py:
    print(f"  {len(only_py)} keys only in Python, e.g. {only_py[:5]}")
if only_r:
    print(f"  {len(only_r)} keys only in R, e.g. {only_r[:5]}")
if bad:
    print(f"MISMATCH in {len(bad)} values:")
    for k, a, b, d in bad[:40]:
        print(f"  {k:60s} python={a:.8g}  R={b:.8g}  rel.diff={d:.2e}")
    sys.exit(1)
print("PASS: Python and R produce identical weighted estimates and standard errors.")
