#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
STARTUP_RHO = os.environ.get("STARTUP_RHO", "7.009816816733094e-6")

subprocess.run(["python3", "prepare_fast_child.py"], cwd=HERE, check=True)
subprocess.run(["python3", "prepare_heavy_parent.py"], cwd=HERE, check=True)

parent = HERE / "heavy_parent.i"
text = parent.read_text(encoding="utf-8")

# Parent-first staggered ordering:
#   1) advance heavy/ion state over the physical 1 ns parent step using the
#      previously available electrostatic potential (zero on the first cycle),
#   2) at TIMESTEP_END transfer that updated heavy state to the fast child,
#   3) solve the existing fully implicit electron-energy-Poisson child on the
#      now-fixed heavy state,
#   4) transfer the new potential back for the next heavy cycle.
old_flag = "execute_on = TIMESTEP_BEGIN"
count = text.count(old_flag)
if count != 3:
    raise RuntimeError(f"expected 3 TIMESTEP_BEGIN coupling flags, found {count}")
text = text.replace(old_flag, "execute_on = TIMESTEP_END")

old_dt = """  dt = 5.0e-9
  dtmin = 5.0e-9
  dtmax = 5.0e-9
  end_time = 2.0e-8
"""
new_dt = """  dt = 1.0e-9
  dtmin = 1.0e-9
  dtmax = 1.0e-9
  num_steps = 1
  end_time = 1.0e-9
"""
if old_dt not in text:
    raise RuntimeError("generated heavy timestep block not found")
text = text.replace(old_dt, new_dt, 1)

# Keep the snapshot seed exactly consistent with the electron quasi-neutral IC.
text = text.replace("initial_condition = 7.01e-6", f"initial_condition = {STARTUP_RHO}")

parent.write_text(text, encoding="utf-8")

print("prepared parent-first one-cycle diagnostic")
print("  heavy physical dt = 1.0e-9 s")
print("  heavy cycles      = 1")
print("  child solver      = existing fully implicit electron-energy-Poisson")
print("  coupling          = TIMESTEP_END (heavy first, then fixed-heavy child)")
print(f"  startup rho       = {STARTUP_RHO}")
