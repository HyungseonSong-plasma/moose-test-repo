#!/usr/bin/env python3
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Build the qualified one-pass split first, then convert its fast parent into a
# fixed-heavy block Picard iteration:
#   E_k -> (n_e, phi)_k -> E_{k+1} -> ...
subprocess.run(["python3", "prepare_heavy_energy_ep_once.py"], cwd=HERE, check=True)

fast_path = HERE / "fast_child.i"
ep_path = HERE / "electron_poisson_stage.i"
parent_path = HERE / "heavy_parent.i"

fast = fast_path.read_text(encoding="utf-8")

# Return both electrostatic/electron state variables needed by the next energy
# correction. log_energy remains the energy-stage nonlinear variable.
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

# Keep the nested electron-Poisson current iterate across fixed-point passes.
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

# Up to ten block corrections at the same physical t^(n+1). Allow early exit if
# the standard MOOSE fixed-point residual converges; accept the tenth iterate if
# it has not yet reached the strict diagnostic tolerance so the trajectory is
# still available for analysis.
exec_marker = """[Executioner]
  type = Transient
  scheme = implicit-euler
"""
exec_replacement = """[Executioner]
  type = Transient
  scheme = implicit-euler
  fixed_point_min_its = 2
  fixed_point_max_its = 10
  fixed_point_rel_tol = 1.0e-6
  fixed_point_abs_tol = 1.0e-10
  accept_on_max_fixed_point_iteration = true
"""
if exec_marker not in fast:
    raise RuntimeError("fast energy Executioner marker not found")
fast = fast.replace(exec_marker, exec_replacement, 1)

# Record fixed-point count.
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

# Evaluate the diagnostic fields after every NP correction, at the fixed-point
# convergence check. These fields live in the fast parent because potential and
# log_ne are copied back from the electron-Poisson child before that check.
for name in (
    "charge_integral",
    "charge_min",
    "charge_max",
    "n_e_min",
    "n_e_max",
    "energy_density_min",
    "energy_density_max",
    "mean_energy_min",
    "mean_energy_max",
    "phi_min",
    "phi_max",
):
    pat = re.compile(
        rf"(\n  \[{re.escape(name)}\]\n.*?)(    execute_on = 'INITIAL TIMESTEP_END'\n)(  \[\]\n)",
        re.S,
    )
    m = pat.search(fast)
    if not m:
        raise RuntimeError(f"diagnostic postprocessor block not found: {name}")
    fast = fast[:m.start()] + m.group(1) + "    execute_on = 'INITIAL TIMESTEP_END MULTIAPP_FIXED_POINT_CONVERGENCE'\n" + m.group(3) + fast[m.end():]

# Print a postprocessor table on every correction pass. This avoids relying on
# same-time CSV row semantics for the fixed-point trajectory.
outputs_marker = "[Outputs]\n"
fp_console = """[Outputs]
  [fixed_point_console]
    type = Console
    execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'
  []
"""
if outputs_marker not in fast:
    raise RuntimeError("Outputs marker not found")
fast = fast.replace(outputs_marker, fp_console, 1)

fast = fast.replace("output_split/energy", "output_converge/energy")
fast_path.write_text(fast, encoding="utf-8")

ep = ep_path.read_text(encoding="utf-8")
ep = ep.replace("output_split/electron_poisson", "output_converge/electron_poisson")
ep_path.write_text(ep, encoding="utf-8")

parent = parent_path.read_text(encoding="utf-8")
parent = parent.replace("output_split/heavy", "output_converge/heavy")
parent_path.write_text(parent, encoding="utf-8")

print("prepared fixed-heavy energy <-> electron-Poisson convergence diagnostic")
print("  physical heavy step: 1.0 ns")
print("  outer correction: energy -> electron+Poisson")
print("  heavy state: frozen throughout outer corrections")
print("  correction min/max iterations: 2 / 10")
print("  fixed-point relative/absolute tolerance: 1e-6 / 1e-10")
print("  physical time is NOT advanced by correction iterations")
print("  phi/charge/energy diagnostics execute every fixed-point convergence check")
