#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import math
import runpy

HERE = Path(__file__).resolve().parent
HEAVY_GENERATOR = HERE / "prepare_heavy_log_simplex_smoke.py"
HEAVY_INPUT = HERE / "heavy_log_simplex_smoke.i"
OUT = HERE / "full_monolithic_log_simplex.i"

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
M = {"O2": 0.032, "O2s": 0.032, "O2p": 0.032,
     "O": 0.016, "Om": 0.016, "Op": 0.016, "Os": 0.016}


def section_bounds(text: str, section: str) -> tuple[int, int]:
    start = text.find(f"[{section}]\n")
    if start < 0:
        raise RuntimeError(f"missing [{section}] section")
    next_candidates = [
        text.find(f"\n[{name}]\n", start + 1)
        for name in ("Problem", "GlobalParams", "UserObjects", "Variables", "AuxVariables",
                     "AuxKernels", "Functions", "FunctorMaterials", "FVKernels", "FVBCs",
                     "Postprocessors", "Executioner", "Outputs", "Debug")
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

runpy.run_path(str(HEAVY_GENERATOR), run_name="__main__")
text = HEAVY_INPUT.read_text(encoding="utf-8")

pot_aux = child_block(text, "potential_fast")
text = text.replace(pot_aux, "", 1)
text = text.replace("potential_fast", "potential")

mn0 = 1.0 / sum(Y0[s] / M[s] for s in Y0)
rho0 = P0 * mn0 / (R * TG0)
n_o2p = NA * rho0 * Y0["O2p"] / M["O2p"]
n_op = NA * rho0 * Y0["Op"] / M["Op"]
n_om = NA * rho0 * Y0["Om"] / M["Om"]
ne0 = n_o2p + n_op - n_om
log_ne0 = math.log(ne0 / NA)
log_energy0 = math.log((ne0 / NA) * MEAN_E0)

variables = f"""
  [log_ne]
    type = MooseVariableFVReal
    initial_condition = {log_ne0:.17g}
    block = plasma
  []
  [log_energy]
    type = MooseVariableFVReal
    initial_condition = {log_energy0:.17g}
    block = plasma
  []
  [potential]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
"""
text = append_to_section(text, "Variables", variables)

materials = """
  [electron_carrier_constant]
    type = ADGenericFunctorMaterial
    prop_names = 'carrier_one'
    prop_values = '1.0'
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
  [electron_molar_energy_density]
    type = ADParsedFunctorMaterial
    property_name = electron_molar_energy_density
    functor_names = 'log_energy'
    functor_symbols = 'ue'
    expression = 'exp(ue)'
    block = plasma
  []
  [electron_physical_energy_density]
    type = ADParsedFunctorMaterial
    property_name = electron_energy_density_eV_m3
    functor_names = 'electron_molar_energy_density'
    functor_symbols = 'we_mol'
    expression = '6.02214076e23*we_mol'
    block = plasma
  []
  [mean_energy]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = log_energy
    electron_density = log_ne
    state_form = log_molar_eV
    block = plasma
  []
  [electron_transport]
    type = PhysicsElectronTransportLookupMaterial
    property_table_file = '../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'
    mean_energy = mean_en_solved
    pressure = p
    gas_temperature = T_g
    bounds_policy = clamp
    block = plasma
  []
  [O2p_number_density_monolithic]
    type = ADParsedFunctorMaterial
    property_name = n_O2p_monolithic
    functor_names = 'rho_mat w_O2p'
    functor_symbols = 'rhoh frac'
    expression = '6.02214076e23*rhoh*frac/0.032'
    block = plasma
  []
  [Om_number_density_monolithic]
    type = ADParsedFunctorMaterial
    property_name = n_Om_monolithic
    functor_names = 'rho_mat w_Om'
    functor_symbols = 'rhoh frac'
    expression = '6.02214076e23*rhoh*frac/0.016'
    block = plasma
  []
  [Op_number_density_monolithic]
    type = ADParsedFunctorMaterial
    property_name = n_Op_monolithic
    functor_names = 'rho_mat w_Op'
    functor_symbols = 'rhoh frac'
    expression = '6.02214076e23*rhoh*frac/0.016'
    block = plasma
  []
  [charge_number_density_monolithic]
    type = ADParsedFunctorMaterial
    property_name = charge_number_density
    functor_names = 'n_O2p_monolithic n_Op_monolithic n_Om_monolithic n_e_physical'
    functor_symbols = 'np2 np nm ne'
    expression = 'np2+np-nm-ne'
    block = plasma
  []
  [charge_density_monolithic]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.602176634e-19*nq'
    block = plasma
  []
  [poisson_source_monolithic]
    type = ADParsedFunctorMaterial
    property_name = poisson_charge_source
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.8095128179727827e-08*nq'
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
  [electron_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_ne
    potential = potential
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []
  [energy_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_energy
    block = plasma
  []
  [energy_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_energy
    coeff = electron_energy_diffusion
    block = plasma
  []
  [energy_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_energy
    potential = potential
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []
  [energy_joule]
    type = PhysicsFVElectronEnergyJouleHeating
    variable = log_energy
    electron_density = electron_molar_density
    potential = potential
    mobility = electron_mobility
    diffusion = electron_diffusion
    state_form = molar_eV
    block = plasma
  []
  [phi_diffusion]
    type = FVDiffusion
    variable = potential
    coeff = relative_permittivity
    block = plasma
  []
  [phi_charge_source]
    type = FVCoupledForce
    variable = potential
    v = poisson_charge_source
    coef = 1.0
    block = plasma
  []
"""
text = append_to_section(text, "FVKernels", kernels)

bcs = """
  [electron_sheath_loss]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = log_ne
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    mean_electron_energy = mean_en_solved
    potential = potential
    log_molar_state = true
  []
  [electron_energy_sheath_loss]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = log_energy
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    electron_density = electron_molar_density
    mean_electron_energy = mean_en_solved
    potential = potential
    molar_energy_state = true
  []
  [grounded_potential]
    type = FVDirichletBC
    variable = potential
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    value = 0.0
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
  [electron_mean_energy_min]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_mean_energy_max]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_integral_monolithic]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density_C_m3
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_min_monolithic]
    type = ADElementExtremeFunctorValue
    functor = potential
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_max_monolithic]
    type = ADElementExtremeFunctorValue
    functor = potential
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
text = append_to_section(text, "Postprocessors", pps)

text = text.replace("  line_search = none\n", "  line_search = bt\n", 1)
old_petsc = """  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
"""
new_petsc = """  petsc_options = '-snes_converged_reason -snes_monitor -snes_linesearch_monitor -ksp_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type -snes_linesearch_type'
  petsc_options_value = 'preonly lu NONZERO bt'
"""
if old_petsc not in text:
    raise RuntimeError("heavy smoke PETSc block not found")
text = text.replace(old_petsc, new_petsc, 1)
text = text.replace("  nl_abs_tol = 1e-11\n", "  nl_abs_tol = 1e-10\n", 1)
text = text.replace("  nl_max_its = 80\n", "  nl_max_its = 100\n", 1)

if "[Debug]" not in text:
    text += "\n[Debug]\n  show_var_residual_norms = true\n[]\n"

for required in (
    "[eta_O2p]", "[log_ne]", "[log_energy]", "[potential]",
    "type = PhysicsFVLogMassFractionTimeDerivative",
    "type = PhysicsFVLogMolarElectronTimeDerivative",
    "type = PhysicsFVElectronEnergyJouleHeating",
    "property_name = charge_number_density",
    "variable = potential",
):
    if required not in text:
        raise RuntimeError(f"monolithic contract missing: {required}")
if "potential_fast" in text:
    raise RuntimeError("frozen split potential survived monolithic generation")
if "[MultiApps]" in text or "[Transfers]" in text:
    raise RuntimeError("split coupling survived monolithic generation")

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
print("full monolithic heavy-log/simplex + electron-log + Poisson prototype")
print(f"startup Mn={mn0:.17g} rho={rho0:.17g}")
print(f"startup n_O2p={n_o2p:.17g} n_e={ne0:.17g}")
print(f"startup log_ne={log_ne0:.17g} log_energy={log_energy0:.17g}")
print("physical dt = 0.1 ns; chemistry source remains off in this first discriminator")
