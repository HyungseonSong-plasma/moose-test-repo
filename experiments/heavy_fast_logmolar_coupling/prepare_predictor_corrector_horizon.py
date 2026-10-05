#!/usr/bin/env python3
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
END_TIME_NS = float(os.environ.get("END_TIME_NS", "25"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output_horizon")
MAX_CORRECTIONS = int(os.environ.get("MAX_CORRECTIONS", "10"))
STARTUP_RHO = "7.009816816733094e-6"
CHILD_DT_PROPOSAL = "8.0e-9"

if END_TIME_NS <= 0.0:
    raise RuntimeError("END_TIME_NS must be positive")
if MAX_CORRECTIONS < 2:
    raise RuntimeError("MAX_CORRECTIONS must be >= 2")
if not re.fullmatch(r"[A-Za-z0-9_.-]+", OUTPUT_DIR):
    raise RuntimeError("OUTPUT_DIR must be a simple relative directory name")

# Generate the qualified predictor -> heavy -> predictor-seeded corrector case.
# Force the exact heavy/electron startup density so n_e0 = n_O2+0 = 1e16 m^-3.
env = os.environ.copy()
env["MAX_CORRECTIONS"] = str(MAX_CORRECTIONS)
env["STARTUP_RHO"] = STARTUP_RHO
subprocess.run(
    ["python3", "prepare_predictor_corrector_adaptive_dt.py"],
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

end_time_s = END_TIME_NS * 1.0e-9
end_time_text = f"{end_time_s:.17g}"

# All five apps must share the same physical horizon.
for label, path in files.items():
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r"(^\s*end_time\s*=\s*)2\.0e-8\s*$",
        rf"\g<1>{end_time_text}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise RuntimeError(f"{label}: adaptive 20 ns end_time marker not found")
    updated = updated.replace("output_adaptive_fp", OUTPUT_DIR)
    path.write_text(updated, encoding="utf-8")

# The parent owns physical dt selection.  Previously each child advertised
# dt=1 ns, so TransientMultiApp's minimum-dt synchronization silently capped
# parent growth at 1 ns.  Make every child advertise dtmax=8 ns instead; the
# smaller parent dt still wins and is the actual physical step.
child_paths = [
    files["predictor_energy"],
    files["predictor_ep"],
    files["corrector_energy"],
    files["corrector_ep"],
]
child_block_old = (
    "  dt = 1.0e-9\n"
    "  dtmin = 2.5e-10\n"
    "  dtmax = 8.0e-9\n"
)
child_block_new = (
    f"  dt = {CHILD_DT_PROPOSAL}\n"
    "  dtmin = 2.5e-10\n"
    "  dtmax = 8.0e-9\n"
)
for path in child_paths:
    text = path.read_text(encoding="utf-8")
    if text.count(child_block_old) != 1:
        raise RuntimeError(f"{path.name}: child 1 ns dt proposal block not found")
    text = text.replace(child_block_old, child_block_new, 1)
    path.write_text(text, encoding="utf-8")

# Structural guards for the long-horizon jobs.
parent = files["parent"].read_text(encoding="utf-8")
if "type = PhysicsFastFixedPointAdaptiveDT" not in parent:
    raise RuntimeError("parent adaptive timestepper missing")
if f"end_time = {end_time_text}" not in parent:
    raise RuntimeError("parent horizon patch missing")

for path in child_paths:
    text = path.read_text(encoding="utf-8")
    if "  dt = 1.0e-9\n" in text:
        raise RuntimeError(f"{path.name}: 1 ns child dt clamp survived")
    if f"  dt = {CHILD_DT_PROPOSAL}\n" not in text:
        raise RuntimeError(f"{path.name}: dtmax child proposal missing")
    if f"end_time = {end_time_text}" not in text:
        raise RuntimeError(f"{path.name}: horizon patch missing")

fast = files["predictor_energy"].read_text(encoding="utf-8")
if "initial_condition = -17.913538455038942" not in fast:
    raise RuntimeError("exact n_e0=1e16 startup was not propagated")
if "initial_condition = -16.167341364887978" not in fast:
    raise RuntimeError("exact electron-energy startup was not propagated")

print("prepared independent long-horizon adaptive predictor-corrector case")
print(f"  end time: {END_TIME_NS:g} ns")
print(f"  output dir: {OUTPUT_DIR}")
print(f"  exact startup rho: {STARTUP_RHO} kg/m^3")
print("  exact startup n_e = n_O2+ = 1e16 m^-3")
print("  parent adaptive dt: initial=1 ns, min=0.25 ns, max=8 ns")
print("  child dt proposal: 8 ns (no 1 ns growth clamp)")
print(f"  fixed-point max corrections: {MAX_CORRECTIONS}")
