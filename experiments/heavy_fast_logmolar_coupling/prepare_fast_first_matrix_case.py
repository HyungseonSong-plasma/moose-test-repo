#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ION_DT_NS = float(os.environ.get("ION_DT_NS", "1"))
CORRECTIONS = int(os.environ.get("CORRECTIONS", "2"))

if ION_DT_NS <= 0.0:
    raise RuntimeError("ION_DT_NS must be positive")
if CORRECTIONS < 1:
    raise RuntimeError("CORRECTIONS must be >= 1")

DT = ION_DT_NS * 1.0e-9
DT_STR = f"{DT:.16g}"

# Start from the qualified split inputs.  This produces a one-physical-step
# energy block, a nested electron+Poisson block, and the heavy parent.
subprocess.run(["python3", "prepare_heavy_energy_ep_once.py"], cwd=HERE, check=True)

fast_path = HERE / "fast_child.i"
ep_path = HERE / "electron_poisson_stage.i"
parent_path = HERE / "heavy_parent.i"

fast = fast_path.read_text(encoding="utf-8")
ep = ep_path.read_text(encoding="utf-8")
parent = parent_path.read_text(encoding="utf-8")

# -----------------------------------------------------------------------------
# Fast outer block correction:
#   E_1 -> NP_1 -> ... -> E_k -> NP_k
# at the same physical t^(n+1).  Preserve the nested child iterate between
# fixed-point corrections and return both phi and log_ne to the next energy pass.
# -----------------------------------------------------------------------------
old_transfer = """  [ep_potential_to_energy]
    type = MultiAppCopyTransfer
    from_multi_app = electron_poisson
    source_variable = potential
    variable = potential
    execute_on = TIMESTEP_END
  []
"""
new_transfer = """  [ep_state_to_energy]
    type = MultiAppCopyTransfer
    from_multi_app = electron_poisson
    source_variable = 'potential log_ne'
    variable = 'potential log_ne'
    execute_on = TIMESTEP_END
  []
"""
if old_transfer not in fast:
    raise RuntimeError("electron-Poisson return transfer not found")
fast = fast.replace(old_transfer, new_transfer, 1)

needle = """    output_sub_cycles = true
    execute_on = TIMESTEP_END
"""
replacement = """    output_sub_cycles = true
    no_restore = true
    execute_on = TIMESTEP_END
"""
if needle not in fast:
    raise RuntimeError("nested electron-Poisson MultiApp block not found")
fast = fast.replace(needle, replacement, 1)

exec_marker = """[Executioner]
  type = Transient
  scheme = implicit-euler
"""
exec_replacement = f"""[Executioner]
  type = Transient
  scheme = implicit-euler
  fixed_point_min_its = {CORRECTIONS}
  fixed_point_max_its = {CORRECTIONS}
  fixed_point_rel_tol = 1.0e-14
  fixed_point_abs_tol = 1.0e-14
  accept_on_max_fixed_point_iteration = true
"""
if exec_marker not in fast:
    raise RuntimeError("fast Executioner marker not found")
fast = fast.replace(exec_marker, exec_replacement, 1)

pp_marker = "[Postprocessors]\n"
fp_pp = """[Postprocessors]
  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = TIMESTEP_END
  []
"""
if pp_marker not in fast:
    raise RuntimeError("fast Postprocessors marker not found")
fast = fast.replace(pp_marker, fp_pp, 1)

# -----------------------------------------------------------------------------
# Use the SAME physical timestep in energy, electron+Poisson, and heavy.
# Corrections do not add physical time; each pass corrects the same t^(n+1).
# -----------------------------------------------------------------------------
def set_dt(text: str, dt_str: str) -> str:
    replacements = {
        "  dt = 1.0e-9\n": f"  dt = {dt_str}\n",
        "  dtmin = 1.0e-9\n": f"  dtmin = {dt_str}\n",
        "  dtmax = 1.0e-9\n": f"  dtmax = {dt_str}\n",
        "  end_time = 1.0e-9\n": f"  end_time = {dt_str}\n",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"timestep token not found: {old.strip()}")
        text = text.replace(old, new, 1)
    return text

fast = set_dt(fast, DT_STR)
ep = set_dt(ep, DT_STR)
parent = set_dt(parent, DT_STR)

# -----------------------------------------------------------------------------
# Fast-first ordering: transfer H^n to fast, converge the requested number of
# E<->NP corrections, return phi, then advance heavy by one physical ion step.
# -----------------------------------------------------------------------------
old_flag = "execute_on = TIMESTEP_END"
ma_start = parent.find("[MultiApps]\n")
exec_start = parent.find("[Executioner]\n", ma_start)
if ma_start < 0 or exec_start < 0:
    raise RuntimeError("outer MultiApps/Executioner coupling region not found")
region = parent[ma_start:exec_start]
region_count = region.count(old_flag)
if region_count != 3:
    raise RuntimeError(f"expected 3 TIMESTEP_END flags in outer coupling region, found {region_count}")
region = region.replace(old_flag, "execute_on = TIMESTEP_BEGIN")
parent = parent[:ma_start] + region + parent[exec_start:]

# Keep each matrix job self-contained. GitHub matrix jobs have separate workspaces,
# so a common output_matrix directory is safe and simplifies artifact collection.
fast = fast.replace("output_split/energy", "output_matrix/energy")
ep = ep.replace("output_split/electron_poisson", "output_matrix/electron_poisson")
parent = parent.replace("output_split/heavy", "output_matrix/heavy")

fast_path.write_text(fast, encoding="utf-8")
ep_path.write_text(ep, encoding="utf-8")
parent_path.write_text(parent, encoding="utf-8")

print("prepared fast-first matrix case")
print(f"  ion/heavy physical dt: {ION_DT_NS:g} ns")
print(f"  energy physical dt:    {ION_DT_NS:g} ns")
print(f"  electron+Poisson dt:   {ION_DT_NS:g} ns")
print(f"  fixed-point corrections: {CORRECTIONS}")
print("  ordering: [energy -> electron+Poisson] x corrections -> heavy")
print("  heavy state frozen during fast corrections")
print("  corrections do NOT advance physical time")
