#!/usr/bin/env python3
import math
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
END_TIME_NS = float(os.environ.get("END_TIME_NS", "5"))
FIXED_DT_NS = float(os.environ.get("FIXED_DT_NS", "1"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output_fixed_dt")
MAX_CORRECTIONS = int(os.environ.get("MAX_CORRECTIONS", "10"))

if END_TIME_NS <= 0.0:
    raise RuntimeError("END_TIME_NS must be positive")
if FIXED_DT_NS <= 0.0:
    raise RuntimeError("FIXED_DT_NS must be positive")
if MAX_CORRECTIONS < 2:
    raise RuntimeError("MAX_CORRECTIONS must be >= 2")
if not re.fullmatch(r"[A-Za-z0-9_.-]+", OUTPUT_DIR):
    raise RuntimeError("OUTPUT_DIR must be a simple relative directory name")

n_steps = END_TIME_NS / FIXED_DT_NS
if not math.isclose(n_steps, round(n_steps), rel_tol=0.0, abs_tol=1.0e-12):
    raise RuntimeError("END_TIME_NS must be an integer multiple of FIXED_DT_NS")

# Start from the qualified long-horizon predictor -> heavy -> corrector setup.
# This preserves the independently owned corrector old state F^n and exact startup.
env = os.environ.copy()
env["END_TIME_NS"] = f"{END_TIME_NS:.17g}"
env["OUTPUT_DIR"] = OUTPUT_DIR
env["MAX_CORRECTIONS"] = str(MAX_CORRECTIONS)
subprocess.run(
    ["python3", "prepare_predictor_corrector_horizon.py"],
    cwd=HERE,
    check=True,
    env=env,
)

files = {
    "parent": HERE / "heavy_parent.i",
    "predictor_energy": HERE / "fast_child.i",
    "predictor_ep": HERE / "electron_poisson_stage.i",
    "corrector_energy": HERE / "fast_corrector.i",
    "corrector_ep": HERE / "electron_poisson_corrector_stage.i",
}

fixed_dt_s = FIXED_DT_NS * 1.0e-9
fixed_dt_text = f"{fixed_dt_s:.17g}"

# Children must advertise exactly the same physical step as the parent.
child_old = (
    "  dt = 8.0e-9\n"
    "  dtmin = 2.5e-10\n"
    "  dtmax = 8.0e-9\n"
)
child_new = (
    f"  dt = {fixed_dt_text}\n"
    f"  dtmin = {fixed_dt_text}\n"
    f"  dtmax = {fixed_dt_text}\n"
)
for label in ("predictor_energy", "predictor_ep", "corrector_energy", "corrector_ep"):
    path = files[label]
    text = path.read_text(encoding="utf-8")
    if text.count(child_old) != 1:
        raise RuntimeError(f"{label}: adaptive child dt block not found")
    path.write_text(text.replace(child_old, child_new, 1), encoding="utf-8")

# Disable the adaptive parent controller completely.  With no explicit
# TimeStepper block, Transient uses the constant dt supplied below.
parent_path = files["parent"]
parent = parent_path.read_text(encoding="utf-8")
parent_pattern = re.compile(
    r"  dtmin = 2\.5e-10\n"
    r"  dtmax = 8\.0e-9\n"
    r"  auto_advance = false\n"
    r"  \[TimeStepper\]\n"
    r"    type = PhysicsFastFixedPointAdaptiveDT\n"
    r"    predictor_iterations = predictor_fp_iterations\n"
    r"    corrector_iterations = corrector_fp_iterations\n"
    r"    initial_dt = 1\.0e-9\n"
    r"    grow_factor = 1\.5\n"
    r"    shrink_factor = 0\.7\n"
    r"    grow_below_iterations = 8\n"
    r"    shrink_above_iterations = 8\n"
    r"    cutback_factor_at_failure = 0\.5\n"
    r"  \[\]\n"
)
parent_replacement = (
    f"  dt = {fixed_dt_text}\n"
    f"  dtmin = {fixed_dt_text}\n"
    f"  dtmax = {fixed_dt_text}\n"
    "  auto_advance = false\n"
)
parent, count = parent_pattern.subn(parent_replacement, parent, count=1)
if count != 1:
    raise RuntimeError("parent adaptive TimeStepper block not found")
parent_path.write_text(parent, encoding="utf-8")

# Structural guards: this experiment must have no adaptive timestepper left.
for label, path in files.items():
    text = path.read_text(encoding="utf-8")
    if "PhysicsFastFixedPointAdaptiveDT" in text:
        raise RuntimeError(f"{label}: adaptive timestepper survived fixed-dt patch")
    if f"dt = {fixed_dt_text}" not in text:
        raise RuntimeError(f"{label}: fixed dt was not applied")

fast = files["predictor_energy"].read_text(encoding="utf-8")
if "initial_condition = -17.913538455038942" not in fast:
    raise RuntimeError("exact n_e0=1e16 startup was not propagated")
if "initial_condition = -16.167341364887978" not in fast:
    raise RuntimeError("exact electron-energy startup was not propagated")

print("prepared fixed-dt temporal-convergence predictor-corrector case")
print(f"  end time: {END_TIME_NS:g} ns")
print(f"  fixed physical dt: {FIXED_DT_NS:g} ns")
print(f"  exact number of steps: {int(round(n_steps))}")
print(f"  output dir: {OUTPUT_DIR}")
print("  physics/BC/reactions unchanged from baseline horizon case")
print("  exact startup n_e = n_O2+ = 1e16 m^-3")
print(f"  fixed-point max corrections: {MAX_CORRECTIONS}")
