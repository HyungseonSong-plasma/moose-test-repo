#!/usr/bin/env python3
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
STARTUP_RHO = os.environ.get("STARTUP_RHO", "7.009816816733094e-6")

# Start from the already qualified heavy/fast generators so geometry, RZ handling,
# heavy closures, charge closure, and transport lookup remain identical.
subprocess.run(["python3", "prepare_fast_child.py"], cwd=HERE, check=True)
subprocess.run(["python3", "prepare_heavy_parent.py"], cwd=HERE, check=True)

fast_path = HERE / "fast_child.i"
parent_path = HERE / "heavy_parent.i"
full_fast = fast_path.read_text(encoding="utf-8")


def block_pattern(name: str):
    return re.compile(rf"\n  \[{re.escape(name)}\]\n.*?\n  \[\]\n", re.S)


def move_variable_to_aux(text: str, name: str) -> str:
    pat = block_pattern(name)
    m = pat.search(text)
    if not m:
        raise RuntimeError(f"variable block {name} not found")
    block = m.group(0)
    text = text[:m.start()] + "\n" + text[m.end():]
    marker = "[AuxVariables]\n"
    if marker not in text:
        raise RuntimeError("AuxVariables section not found")
    return text.replace(marker, marker + block.lstrip("\n"), 1)


def remove_blocks(text: str, names) -> str:
    for name in names:
        pat = block_pattern(name)
        m = pat.search(text)
        if not m:
            raise RuntimeError(f"block {name} not found")
        text = text[:m.start()] + "\n" + text[m.end():]
    return text


def set_one_ns(text: str, nl_max_its: int = 80) -> str:
    replacements = {
        "  dt = 1.0e-9\n": "  dt = 1.0e-9\n",
        "  dtmin = 1.0e-9\n": "  dtmin = 1.0e-9\n",
        "  dtmax = 1.0e-9\n": "  dtmax = 1.0e-9\n",
        "  num_steps = 10\n": "  num_steps = 1\n",
        "  end_time = 1.0e-8\n": "  end_time = 1.0e-9\n",
        "  nl_rel_tol = 1.0e-10\n": "  nl_rel_tol = 1.0e-9\n",
        "  nl_abs_tol = 1.0e-12\n": "  nl_abs_tol = 1.0e-10\n",
        "  nl_max_its = 30\n": f"  nl_max_its = {nl_max_its}\n",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"executioner token not found: {old.strip()}")
        text = text.replace(old, new, 1)
    return text


# -----------------------------------------------------------------------------
# Stage 3: electron continuity + Poisson, with heavy state and log_energy frozen.
# -----------------------------------------------------------------------------
ep = full_fast
ep = move_variable_to_aux(ep, "log_energy")
ep = remove_blocks(
    ep,
    [
        "energy_time",
        "energy_diffusion",
        "energy_drift",
        "energy_joule",
        "electron_energy_sheath_loss",
    ],
)
ep = set_one_ns(ep)
ep = ep.replace(
    "[Outputs]\n  exodus = true\n  csv = true\n",
    "[Outputs]\n  file_base = 'output_split/electron_poisson'\n  exodus = true\n  csv = true\n",
    1,
)
ep += "\n[Debug]\n  show_var_residual_norms = true\n[]\n"
(HERE / "electron_poisson_stage.i").write_text(ep, encoding="utf-8")

# -----------------------------------------------------------------------------
# Stage 2: electron-energy equation only. log_ne and potential are frozen at the
# previous electron/field state. Thus Joule work uses the old/frozen E and n_e.
# The updated heavy state is transferred in by the parent before this solve.
# -----------------------------------------------------------------------------
energy = full_fast
energy = move_variable_to_aux(energy, "log_ne")
energy = move_variable_to_aux(energy, "potential")
energy = remove_blocks(
    energy,
    [
        "electron_time",
        "electron_diffusion",
        "electron_drift",
        "phi_diffusion",
        "phi_charge_source",
        "electron_sheath_loss",
        "grounded_potential",
    ],
)
energy = set_one_ns(energy)

nested = """
[MultiApps]
  [electron_poisson]
    type = TransientMultiApp
    input_files = 'electron_poisson_stage.i'
    sub_cycling = false
    interpolate_transfers = false
    output_sub_cycles = true
    execute_on = TIMESTEP_END
  []
[]

[Transfers]
  [energy_heavy_state_to_ep]
    type = MultiAppCopyTransfer
    to_multi_app = electron_poisson
    source_variable = 'log_ne log_energy potential p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
    variable = 'log_ne log_energy potential p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
    execute_on = TIMESTEP_END
  []
  [ep_potential_to_energy]
    type = MultiAppCopyTransfer
    from_multi_app = electron_poisson
    source_variable = potential
    variable = potential
    execute_on = TIMESTEP_END
  []
[]

"""
marker = "[Executioner]\n"
if marker not in energy:
    raise RuntimeError("energy Executioner marker not found")
energy = energy.replace(marker, nested + marker, 1)
energy = energy.replace(
    "[Outputs]\n  exodus = true\n  csv = true\n",
    "[Outputs]\n  file_base = 'output_split/energy'\n  exodus = true\n  csv = true\n",
    1,
)
energy += "\n[Debug]\n  show_var_residual_norms = true\n[]\n"
fast_path.write_text(energy, encoding="utf-8")

# -----------------------------------------------------------------------------
# Stage 1: advance the heavy system by one physical 1 ns step first. At its
# TIMESTEP_END the updated heavy state is transferred into the energy stage.
# -----------------------------------------------------------------------------
parent = parent_path.read_text(encoding="utf-8")
old_flag = "execute_on = TIMESTEP_BEGIN"
count = parent.count(old_flag)
if count != 3:
    raise RuntimeError(f"expected 3 TIMESTEP_BEGIN coupling flags, found {count}")
parent = parent.replace(old_flag, "execute_on = TIMESTEP_END")

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
if old_dt not in parent:
    raise RuntimeError("generated heavy timestep block not found")
parent = parent.replace(old_dt, new_dt, 1)
parent = parent.replace("initial_condition = 7.01e-6", f"initial_condition = {STARTUP_RHO}")
parent = parent.replace(
    "[Outputs]\n  csv = true\n  exodus = true\n",
    "[Outputs]\n  file_base = 'output_split/heavy'\n  csv = true\n  exodus = true\n",
    1,
)
parent_path.write_text(parent, encoding="utf-8")

print("prepared uncorrected three-stage split diagnostic")
print("  stage 1: heavy advance             dt = 1.0 ns")
print("  stage 2: electron energy only      dt = 1.0 ns; n_e and phi frozen")
print("  stage 3: electron + Poisson        dt = 1.0 ns; heavy and energy frozen")
print("  correction: disabled")
print(f"  startup rho: {STARTUP_RHO}")
