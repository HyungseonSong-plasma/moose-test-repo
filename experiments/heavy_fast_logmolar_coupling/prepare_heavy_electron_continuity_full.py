#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import math
import runpy

HERE = Path(__file__).resolve().parent
HEAVY_GENERATOR = HERE / "prepare_heavy_log_simplex_smoke.py"
HEAVY_INPUT = HERE / "heavy_log_simplex_smoke.i"
OUT = HERE / "heavy_electron_continuity_full.i"

NA = 6.02214076e23
R = 8.31446
P0 = 1.33322
TG0 = 600.0
MEAN_E0 = 5.73276
Y0 = {
    "O2": 0.7299241959504238,
    "O2s": 0.05,
    "O2p": 7.580404957618788e-5,
    "O": 0.1,
    "Om": 1.0e-30,
    "Op": 1.0e-30,
    "Os": 0.12,
}
M = {
    "O2": 0.032,
    "O2s": 0.032,
    "O2p": 0.032,
    "O": 0.016,
    "Om": 0.016,
    "Op": 0.016,
    "Os": 0.016,
}


def section_bounds(text: str, section: str) -> tuple[int, int]:
    start = text.find(f"[{section}]\n")
    if start < 0:
        raise RuntimeError(f"missing [{section}] section")
    next_candidates = [
        text.find(f"\n[{name}]\n", start + 1)
        for name in (
            "Problem", "GlobalParams", "UserObjects", "Variables", "AuxVariables",
            "AuxKernels", "Functions", "FunctorMaterials", "FVKernels", "FVBCs",
            "Postprocessors", "Executioner", "Preconditioning", "Outputs", "Debug",
        )
    ]
    next_candidates = [x for x in next_candidates if x > start]
    end = min(next_candidates) if next_candidates else len(text)
    return start, end


def append_to_section(text: str, section: str, payload: str) -> str:
    start, end = section_bounds(text, section)
    body = text[start:end]
    close = body.rfind("[]")
    if close < 0:
        raise RuntimeError(f"missing closing [] for [{section}]")
    body = body[:close] + payload.rstrip() + "\n" + body[close:]
    return text[:start] + body + text[end:]


def child_block(text: str, name: str) -> str:
    marker = f"  [{name}]\n"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f"missing block [{name}]")
    end = text.find("  []\n", start + len(marker))
    if end < 0:
        raise RuntimeError(f"unterminated block [{name}]")
    return text[start:end + 5]


def remove_child(text: str, name: str, required: bool = True) -> str:
    marker = f"  [{name}]\n"
    if marker not in text:
        if required:
            raise RuntimeError(f"missing removable block [{name}]")
        return text
    return text.replace(child_block(text, name), "", 1)


runpy.run_path(str(HEAVY_GENERATOR), run_name="__main__")
text = HEAVY_INPUT.read_text(encoding="utf-8")

# -----------------------------------------------------------------------------
# Discriminator physics:
#   heavy flow + heavy log-simplex transport + electron continuity only.
# Bulk electrostatic drift/migration is explicitly removed. No electron-energy
# equation and no Poisson equation are solved.  The grounded electron sheath
# collection BC remains active, evaluated against a frozen 0 V potential_fast.
# -----------------------------------------------------------------------------
for name in (
    "O2p_electrostatic_drift",
    "Om_electrostatic_drift",
    "Op_electrostatic_drift",
    "O2s_heavy_mass_em_correction",
    "O2p_heavy_mass_em_correction",
    "O_heavy_mass_em_correction",
    "Om_heavy_mass_em_correction",
    "Op_heavy_mass_em_correction",
    "Os_heavy_mass_em_correction",
):
    text = remove_child(text, name)

# Remove the E-driven heavy-ion wall-loss path and its diagnostics. Keep
# potential_fast itself as a frozen 0 V AuxVariable for the electron sheath BC.
for name in (
    "O2p_wall_flux_feedback",
    "O2p_migration_wall_loss",
    "O2p_migration_mass_loss_rate",
    "O2p_migration_current",
    "potential_fast_min",
    "potential_fast_max",
):
    text = remove_child(text, name, required=False)

mn0 = 1.0 / sum(Y0[s] / M[s] for s in Y0)
rho0 = P0 * mn0 / (R * TG0)
n_o2p = NA * rho0 * Y0["O2p"] / M["O2p"]
n_op = NA * rho0 * Y0["Op"] / M["Op"]
n_om = NA * rho0 * Y0["Om"] / M["Om"]
ne0 = n_o2p + n_op - n_om
log_ne0 = math.log(ne0 / NA)

variables = f"""
  [log_ne]
    type = MooseVariableFVReal
    initial_condition = {log_ne0:.17g}
    block = plasma
  []
"""
text = append_to_section(text, "Variables", variables)

materials = f"""
  [electron_fixed_mean_energy]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en_fixed'
    prop_values = '{MEAN_E0:.17g}'
    block = plasma
  []
  [electron_molar_density]
    type = ADParsedFunctorMaterial
    property_name = electron_molar_density
    functor_names = 'log_ne'
    functor_symbols = 'u'
    expression = 'exp(u)'
    block = plasma
  []
  [electron_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'electron_molar_density'
    functor_symbols = 'ce'
    expression = '6.02214076e23*ce'
    block = plasma
  []
  [electron_transport_continuity_only]
    type = PhysicsElectronTransportLookupMaterial
    property_table_file = '../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'
    mean_energy = mean_en_fixed
    pressure = p
    gas_temperature = T_g
    bounds_policy = clamp
    block = plasma
  []
"""
text = append_to_section(text, "FunctorMaterials", materials)

kernels = """
  [electron_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ne
    block = plasma
  []
  [electron_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ne
    coeff = electron_diffusion
    block = plasma
  []
"""
text = append_to_section(text, "FVKernels", kernels)

# Preserve the physical electron wall loss while keeping bulk E-drift disabled.
# potential_fast is frozen at its 0 V initial condition because the smoke parent
# removes MultiApps/Transfers and this discriminator does not solve Poisson.
bcs = """
  [electron_sheath_loss]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = log_ne
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    mean_electron_energy = mean_en_fixed
    potential = potential_fast
    log_molar_state = true
  []
"""
text = append_to_section(text, "FVBCs", bcs)

pps = """
  [electron_n_min]
    type = ADElementExtremeFunctorValue
    functor = n_e_physical
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_n_max]
    type = ADElementExtremeFunctorValue
    functor = n_e_physical
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
text = append_to_section(text, "Postprocessors", pps)

# Requested A/B physical step: one 1 ns step.
old_time = """  dt = 1.0e-10
  dtmin = 1.0e-10
  dtmax = 1.0e-10
  end_time = 1.0e-10
"""
new_time = """  dt = 1.0e-9
  dtmin = 1.0e-9
  dtmax = 1.0e-9
  end_time = 1.0e-9
"""
if old_time not in text:
    raise RuntimeError("heavy-log 0.1 ns timing block not found")
text = text.replace(old_time, new_time, 1)

# Full/global baseline: one monolithic Newton system with global sparse LU.
text = text.replace("  line_search = none\n", "  line_search = bt\n", 1)
old_petsc = """  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
"""
new_petsc = """  petsc_options = '-snes_converged_reason -snes_monitor -snes_linesearch_monitor -ksp_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type -snes_linesearch_type'
  petsc_options_value = 'preonly lu NONZERO bt'
"""
if old_petsc not in text:
    raise RuntimeError("heavy-log PETSc block not found")
text = text.replace(old_petsc, new_petsc, 1)

if "[Debug]" not in text:
    text += "\n[Debug]\n  show_var_residual_norms = true\n[]\n"

# Structural guards for this exact discriminator.
for required in (
    "[eta_O2p]",
    "[log_ne]",
    "type = PhysicsFVLogMolarElectronTimeDerivative",
    "type = PhysicsFVLogMolarElectronDiffusion",
    "type = PhysicsFVElectronGroundedSheathCollectionBC",
    "mean_electron_energy = mean_en_fixed",
    "potential = potential_fast",
    "dt = 1.0e-9",
    "preonly lu NONZERO bt",
):
    if required not in text:
        raise RuntimeError(f"heavy+electron full contract missing: {required}")
for forbidden in (
    "PhysicsFVLogMolarElectrostaticDrift",
    "PhysicsFVElectronEnergyJouleHeating",
    "[log_energy]",
    "[potential]\n",
    "_electrostatic_drift]",
    "_heavy_mass_em_correction]",
    "O2p_migration_wall_loss",
):
    if forbidden in text:
        raise RuntimeError(f"drift/fast-physics token survived discriminator: {forbidden}")
if "[Preconditioning]" in text:
    raise RuntimeError("FieldSplit unexpectedly present in full/global baseline")

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
print("heavy + electron continuity-only global-LU discriminator")
print("bulk electrostatic drift/migration disabled; electron energy and Poisson absent")
print("electron grounded-sheath collection BC active with frozen potential_fast = 0 V")
print(f"startup n_e={ne0:.17g}; fixed mean energy={MEAN_E0:.17g} eV")
print("physical dt = 1 ns; one step")
