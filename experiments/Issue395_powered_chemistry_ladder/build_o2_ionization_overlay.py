#!/usr/bin/env python3
"""Build Issue #395 EI16-only O2 ionization overlay.

This overlay is intentionally ionization-only so it can be composed with the
separate EI02 elastic and source-backed O2 dissociation overlays without
creating duplicate progress owners.
"""
from __future__ import annotations

import argparse
from pathlib import Path

M_O2 = 0.032
EI16_LOSS_EV = 12.06


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--ei16-table", default="o2_ionization.txt")
    a = p.parse_args()

    base = a.base_input.read_text(encoding="utf-8")
    required = (
        "property_name = n_e_physical",
        "mean_energy = mean_en_solved",
        "property_name = rho_neutral",
        "property_name = w_O2_constraint",
        "[log_ne]",
        "[log_ni]",
        "[log_energy]",
        "[p]",
    )
    missing = [x for x in required if x not in base]
    if missing:
        raise RuntimeError(f"EI16 base-input capability audit failed; missing {missing}")
    if "R_ion_O2" in base or "PhysicsElectronImpactIonizationMaterial" in base:
        raise RuntimeError("EI16 requires no inherited O2-ionization owner")

    text = f'''# Issue #395: EI16 O2 ionization only
[FunctorMaterials]
  [ei16_o2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2_EI16
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/{M_O2:.17g}'
    block = plasma
  []
  [ei16_progress]
    type = PhysicsElectronImpactIonizationMaterial
    rate_table_file = {a.ei16_table}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2_EI16
    block = plasma
  []
  [ei16_electron_source]
    type = ADParsedFunctorMaterial
    property_name = S_electron_molar_EI16
    functor_names = 'R_ion_O2'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [ei16_o2p_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_molar_EI16
    functor_names = 'R_ion_O2'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [ei16_neutral_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_EI16
    functor_names = 'R_ion_O2'
    functor_symbols = 'R'
    expression = '-{M_O2:.17g}*R'
    block = plasma
  []
  [ei16_o2p_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_mass_EI16
    functor_names = 'R_ion_O2'
    functor_symbols = 'R'
    expression = '{M_O2:.17g}*R'
    block = plasma
  []
  [ei16_energy_source]
    type = ADParsedFunctorMaterial
    property_name = S_electron_energy_molar_EI16
    functor_names = 'R_ion_O2'
    functor_symbols = 'R'
    expression = '-{EI16_LOSS_EV:.17g}*R'
    block = plasma
  []
  [ei16_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_EI16
    functor_names = 'S_neutral_mass_EI16 S_O2p_mass_EI16'
    functor_symbols = 'Sn Si'
    expression = 'Sn+Si'
    block = plasma
  []
  [ei16_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_molar_closure_EI16
    functor_names = 'S_electron_molar_EI16 S_O2p_molar_EI16'
    functor_symbols = 'Se Si'
    expression = 'Si-Se'
    block = plasma
  []
[]

[Kernels]
  [ei16_electron_particle_source]
    type = FunctorKernel
    variable = log_ne
    functor = S_electron_molar_EI16
    functor_on_rhs = true
    block = plasma
  []
  [ei16_electron_energy_source]
    type = FunctorKernel
    variable = log_energy
    functor = S_electron_energy_molar_EI16
    functor_on_rhs = true
    block = plasma
  []
[]

[FVKernels]
  [ei16_o2p_source]
    type = FVCoupledForce
    variable = log_ni
    v = S_O2p_molar_EI16
    coef = 1.0
    block = plasma
  []
  [ei16_neutral_mass_source]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_EI16
    coef = 1.0
    block = plasma
  []
[]

[Postprocessors]
  [ei16_R_ion_O2_min]
    type = ADElementExtremeFunctorValue
    functor = R_ion_O2
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei16_R_ion_O2_max]
    type = ADElementExtremeFunctorValue
    functor = R_ion_O2
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei16_R_ion_O2_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_ion_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei16_energy_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_electron_energy_molar_EI16
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei16_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_EI16
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei16_charge_molar_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_molar_closure_EI16
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
'''
    a.output.write_text(text, encoding="utf-8")
    print("ISSUE395_EI16_ONLY_OVERLAY_BUILD_PASS")
    print(f"loss_eV_per_event={EI16_LOSS_EV:.17g}")
    print(f"output={a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
