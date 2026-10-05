#!/usr/bin/env python3
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Generate the already-converged one-pass split first:
#   heavy(1 ns) -> energy(1 ns, n_e/phi frozen) -> electron+Poisson(1 ns, energy frozen)
subprocess.run(["python3", "prepare_heavy_energy_ep_once.py"], cwd=HERE, check=True)

fast_path = HERE / "fast_child.i"
ep_path = HERE / "electron_poisson_stage.i"
parent_path = HERE / "heavy_parent.i"

fast = fast_path.read_text(encoding="utf-8")

# The electron+Poisson child must return both fast variables needed by the next
# energy correction.  log_energy remains the energy-stage nonlinear variable.
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

# Preserve the child iterate across the fast-parent fixed-point corrections.
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

# Force exactly two block Gauss-Seidel passes at the same physical t^(n+1):
#   E1 -> NP1 -> E2 -> NP2.
# The time derivatives continue to reference the same physical old state t^n;
# fixed-point iteration changes only the current t^(n+1) iterate.
exec_marker = """[Executioner]
  type = Transient
  scheme = implicit-euler
"""
exec_replacement = """[Executioner]
  type = Transient
  scheme = implicit-euler
  fixed_point_min_its = 2
  fixed_point_max_its = 2
  fixed_point_rel_tol = 1.0e-14
  fixed_point_abs_tol = 1.0e-14
  accept_on_max_fixed_point_iteration = true
"""
if exec_marker not in fast:
    raise RuntimeError("fast energy Executioner marker not found")
fast = fast.replace(exec_marker, exec_replacement, 1)

# Record how many outer correction passes actually executed.
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

fast = fast.replace("output_split/energy", "output_correction/energy")
fast_path.write_text(fast, encoding="utf-8")

ep = ep_path.read_text(encoding="utf-8")
ep = ep.replace("output_split/electron_poisson", "output_correction/electron_poisson")
ep_path.write_text(ep, encoding="utf-8")

parent = parent_path.read_text(encoding="utf-8")
parent = parent.replace("output_split/heavy", "output_correction/heavy")
parent_path.write_text(parent, encoding="utf-8")

print("prepared two-pass block correction diagnostic")
print("  physical heavy step: 1.0 ns")
print("  correction pass 1: energy -> electron+Poisson")
print("  correction pass 2: energy -> electron+Poisson")
print("  heavy state: frozen throughout both correction passes")
print("  physical time is NOT advanced by the correction pass")
print("  compare final phi_min against one-pass baseline -1.758531948 V")
