#!/usr/bin/env python3
"""Build Issue #395 EI02-only O2 elastic electron-energy-loss overlay."""
from __future__ import annotations

import argparse
from pathlib import Path

M_O2 = 0.032
ME = 9.1093837015e-31
NA = 6.02214076e23
KB_OVER_E = 8.617333262145e-5
ELASTIC_FACTOR = 3.0 * ME / (M_O2 / NA)

REQUIRED_BASE_TOKENS = (
    "[log_ne]",
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
    p.add_argument("--elastic-table", default="o2_elastic.txt")
    return p.parse_args()

def main() -> int:
    a = args()
    base = a.base_input.read_text(encoding="utf-8")
    missing = [x for x in REQUIRED_BASE_TOKENS if x not in base]
    if missing:
        raise RuntimeError(f"EI02 base-input capability audit failed; missing {missing}")
    inherited = [x for x in ("R_elastic_O2", "R_diss_O2", "R_ion_O2") if x in base]
    if inherited:
        raise RuntimeError(f"EI02 requires chemistry-off upstream baseline; found {inherited}")

    text = f"""# Issue #395: EI02 O2 elastic electron-energy loss only.
# No dissociation, ionization, attachment, excitation, or heavy-species source.
[FunctorMaterials]
  [ei02_o2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2_EI02
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/{M_O2:.17g}'
    block = plasma
  []
  [ei02_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = {a.elastic_table}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2_EI02
    reaction_progress = R_elastic_O2
    block = plasma
  []
  [ei02_delta_e]
    type = ADParsedFunctorMaterial
    property_name = delta_epsilon_EI02_eV
    functor_names = 'mean_en_solved T_g_fixed'
    functor_symbols = 'eps Tg'
    expression = '{ELASTIC_FACTOR:.17g}*((2.0/3.0)*eps-{KB_OVER_E:.17g}*Tg)'
    block = plasma
  []
  [ei02_energy_source]
    type = ADParsedFunctorMaterial
    property_name = elastic_energy_source_EI02
    functor_names = 'delta_epsilon_EI02_eV R_elastic_O2'
    functor_symbols = 'de R'
    expression = '-de*R'
    block = plasma
  []
[]

[Kernels]
  [ei02_electron_energy_loss]
    type = FunctorKernel
    variable = log_energy
    functor = elastic_energy_source_EI02
    functor_on_rhs = true
    block = plasma
  []
[]

[Postprocessors]
  [elastic_R_min]
    type = ADElementExtremeFunctorValue
    functor = R_elastic_O2
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_R_max]
    type = ADElementExtremeFunctorValue
    functor = R_elastic_O2
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_R_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_elastic_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_delta_e_min]
    type = ADElementExtremeFunctorValue
    functor = delta_epsilon_EI02_eV
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_delta_e_max]
    type = ADElementExtremeFunctorValue
    functor = delta_epsilon_EI02_eV
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_energy_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = elastic_energy_source_EI02
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""
    leaked = [x for x in ("R_diss_O2", "diss_energy", "12.62", "R_ion_O2") if x in text]
    if leaked:
        raise RuntimeError(f"forbidden non-elastic chemistry leaked into EI02 overlay: {leaked}")
    a.output.write_text(text, encoding="utf-8")
    print("ISSUE395_EI02_ELASTIC_OVERLAY_BUILD_PASS")
    print(f"elastic_factor={ELASTIC_FACTOR:.17g}")
    print(f"output={a.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
