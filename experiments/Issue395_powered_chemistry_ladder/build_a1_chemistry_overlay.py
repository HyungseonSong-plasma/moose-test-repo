#!/usr/bin/env python3
"""Build Issue #395 A1 overlay: EI02 elastic + EI16 O2 ionization only."""
from __future__ import annotations

import argparse
from pathlib import Path

M_O2 = 0.032
ME = 9.1093837015e-31
NA = 6.02214076e23
KB_OVER_E = 8.617333262145e-5
ELASTIC_FACTOR = 3.0 * ME / (M_O2 / NA)
EI16_LOSS_EV = 12.06

REQUIRED_BASE_TOKENS = (
    "[log_ne]",
    "[log_ni]",
    "[log_energy]",
    "[p]",
    "property_name = n_e_physical",
    "type = PhysicsElectronMeanEnergyMaterial",
    "mean_energy = mean_en_solved",
    "property_name = rho_neutral",
    "property_name = w_O2_constraint",
    "T_g_fixed",
    "type = PhysicsFEMLogMolarTimeDerivative",
    "type = PhysicsFVLogMolarElectronTimeDerivative",
)


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--base-input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--ei02-table", default="o2_elastic.txt")
    p.add_argument("--ei16-table", default="o2_ionization.txt")
    return p.parse_args()


def main() -> int:
    a = args()
    base = a.base_input.read_text(encoding="utf-8")
    missing = [x for x in REQUIRED_BASE_TOKENS if x not in base]
    if missing:
        raise RuntimeError(f"A1 base-input capability audit failed; missing {missing}")
    inherited = [x for x in ("R_elastic_O2", "R_ion_O2", "PhysicsElectronImpactIonizationMaterial") if x in base]
    if inherited:
        raise RuntimeError(f"A1 requires chemistry-off upstream baseline; found {inherited}")

    text = f'''# Issue #395 A1: EI02 + EI16 only
[FunctorMaterials]
  [a1_o2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2_A1
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/{M_O2:.17g}'
    block = plasma
  []
  [a1_ei02_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = {a.ei02_table}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2_A1
    reaction_progress = R_elastic_O2
    block = plasma
  []
  [a1_ei16_progress]
    type = PhysicsElectronImpactIonizationMaterial
    rate_table_file = {a.ei16_table}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2_A1
    block = plasma
  []
  [a1_ei02_delta_e]
    type = ADParsedFunctorMaterial
    property_name = delta_epsilon_EI02_eV
    functor_names = 'mean_en_solved T_g_fixed'
    functor_symbols = 'eps Tg'
    expression = '{ELASTIC_FACTOR:.17g}*((2.0/3.0)*eps-{KB_OVER_E:.17g}*Tg)'
    block = plasma
  []
  [a1_electron_source]
    type = ADParsedFunctorMaterial
    property_name = S_electron_molar_A1
    functor_names = 'R_ion_O2'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [a1_o2p_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_molar_A1
    functor_names = 'R_ion_O2'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [a1_neutral_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_A1
    functor_names = 'R_ion_O2'
    functor_symbols = 'R'
    expression = '-{M_O2:.17g}*R'
    block = plasma
  []
  [a1_o2p_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_mass_A1
    functor_names = 'R_ion_O2'
    functor_symbols = 'R'
    expression = '{M_O2:.17g}*R'
    block = plasma
  []
  [a1_energy_source]
    type = ADParsedFunctorMaterial
    property_name = S_electron_energy_molar_A1
    functor_names = 'delta_epsilon_EI02_eV R_elastic_O2 R_ion_O2'
    functor_symbols = 'de Rel Rion'
    expression = '-de*Rel-{EI16_LOSS_EV:.17g}*Rion'
    block = plasma
  []
  [a1_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_A1
    functor_names = 'S_neutral_mass_A1 S_O2p_mass_A1'
    functor_symbols = 'Sn Si'
    expression = 'Sn+Si'
    block = plasma
  []
  [a1_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_molar_closure_A1
    functor_names = 'S_electron_molar_A1 S_O2p_molar_A1'
    functor_symbols = 'Se Si'
    expression = 'Si-Se'
    block = plasma
  []
[]

[Kernels]
  [a1_electron_particle_source]
    type = FunctorKernel
    variable = log_ne
    functor = S_electron_molar_A1
    functor_on_rhs = true
    block = plasma
  []
  [a1_electron_energy_source]
    type = FunctorKernel
    variable = log_energy
    functor = S_electron_energy_molar_A1
    functor_on_rhs = true
    block = plasma
  []
[]

[FVKernels]
  [a1_o2p_source]
    type = FVCoupledForce
    variable = log_ni
    v = S_O2p_molar_A1
    coef = 1.0
    block = plasma
  []
  [a1_neutral_mass_source]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_A1
    coef = 1.0
    block = plasma
  []
[]

[Postprocessors]
  [a1_R_elastic_O2_min]
    type = ADElementExtremeFunctorValue
    functor = R_elastic_O2
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [a1_R_elastic_O2_max]
    type = ADElementExtremeFunctorValue
    functor = R_elastic_O2
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [a1_R_ion_O2_min]
    type = ADElementExtremeFunctorValue
    functor = R_ion_O2
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [a1_R_ion_O2_max]
    type = ADElementExtremeFunctorValue
    functor = R_ion_O2
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [a1_R_ion_O2_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_ion_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [a1_energy_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_electron_energy_molar_A1
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [a1_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_A1
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [a1_charge_molar_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_molar_closure_A1
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
'''
    a.output.write_text(text, encoding="utf-8")
    print("ISSUE395_A1_OVERLAY_BUILD_PASS")
    print(f"elastic_factor={ELASTIC_FACTOR:.17g}")
    print(f"output={a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
