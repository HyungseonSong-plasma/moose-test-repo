#!/usr/bin/env python3
"""Build Issue #395 EI01-only O2 dissociative attachment overlay.

e + O2 -> O + O-

One progress R_attachment [mol/(m^3 s)] owns all projections:
  electron: -R_attachment
  O-:       +R_attachment
  O:        +R_attachment
  O2:       -R_attachment (implicit constrained-neutral closure)
  neutral total mass: -M_O*R_attachment (O- takes the other M_O)
Electron-energy source is exactly absent: canonical 0-eV model convention.
"""
from __future__ import annotations

import argparse
from pathlib import Path

M_O = 0.016
M_O2 = 0.032


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attachment-table", default="o2_attachment.txt")
    args = parser.parse_args()

    base = args.base_input.read_text(encoding="utf-8")
    required = (
        "property_name = n_e_physical",
        "mean_energy = mean_en_solved",
        "property_name = rho_neutral",
        "property_name = w_O2_constraint",
        "[log_ne]",
        "[log_nm]",
        "[w_O]",
        "[p]",
    )
    missing = [token for token in required if token not in base]
    if missing:
        raise RuntimeError(f"EI01 base input capability audit failed: {missing}")
    if "R_attachment" in base:
        raise RuntimeError("EI01 requires no inherited attachment progress owner")

    text = f'''# Issue #395: EI01 O2 dissociative attachment only
# e + O2 -> O + O-
# 0 eV explicit electron-energy loss (canonical source convention)
# O2 is constrained by the neutral-mixture composition; no independent O2 kernel.
[FunctorMaterials]
  [ei01_o2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2_EI01
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/{M_O2:.17g}'
    block = plasma
  []
  [ei01_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = {args.attachment_table}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2_EI01
    reaction_progress = R_attachment
    block = plasma
  []
  [ei01_electron_source]
    type = ADParsedFunctorMaterial
    property_name = S_electron_molar_EI01
    functor_names = 'R_attachment'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [ei01_om_source]
    type = ADParsedFunctorMaterial
    property_name = S_Om_molar_EI01
    functor_names = 'R_attachment'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [ei01_o_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI01
    functor_names = 'R_attachment'
    functor_symbols = 'R'
    expression = '{M_O:.17g}*R'
    block = plasma
  []
  [ei01_om_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_Om_mass_EI01
    functor_names = 'R_attachment'
    functor_symbols = 'R'
    expression = '{M_O:.17g}*R'
    block = plasma
  []
  [ei01_o2_mass_source_implicit]
    type = ADParsedFunctorMaterial
    property_name = S_O2_mass_implicit_EI01
    functor_names = 'R_attachment'
    functor_symbols = 'R'
    expression = '-{M_O2:.17g}*R'
    block = plasma
  []
  [ei01_neutral_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_EI01
    functor_names = 'R_attachment'
    functor_symbols = 'R'
    expression = '-{M_O:.17g}*R'
    block = plasma
  []
  [ei01_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_EI01
    functor_names = 'S_O2_mass_implicit_EI01 S_O_mass_EI01 S_Om_mass_EI01'
    functor_symbols = 'So2 So Som'
    expression = 'So2+So+Som'
    block = plasma
  []
  [ei01_charge_molar_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_molar_closure_EI01
    functor_names = 'S_electron_molar_EI01 S_Om_molar_EI01'
    functor_symbols = 'Se Som'
    expression = 'Se+Som'
    block = plasma
  []
[]

[Kernels]
  [ei01_electron_particle_sink]
    type = FunctorKernel
    variable = log_ne
    functor = S_electron_molar_EI01
    functor_on_rhs = true
    block = plasma
  []
[]

[FVKernels]
  [ei01_atomic_oxygen_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI01
    block = plasma
  []
  [ei01_negative_ion_source]
    type = FVCoupledForce
    variable = log_nm
    v = S_Om_molar_EI01
    coef = 1.0
    block = plasma
  []
  [ei01_neutral_mass_sink]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_EI01
    coef = 1.0
    block = plasma
  []
[]

[Postprocessors]
  [ei01_R_min]
    type = ADElementExtremeFunctorValue
    functor = R_attachment
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei01_R_max]
    type = ADElementExtremeFunctorValue
    functor = R_attachment
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei01_R_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_attachment
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei01_electron_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_electron_molar_EI01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei01_om_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_Om_molar_EI01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei01_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_EI01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei01_charge_molar_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_molar_closure_EI01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
'''
    if text.count("reaction_progress = R_attachment") != 1:
        raise AssertionError("EI01 must have exactly one kinetic owner")
    if "[ei01_electron_energy_source]" in text:
        raise AssertionError("EI01 canonical zero-loss convention violated")
    args.output.write_text(text, encoding="utf-8")
    print("ISSUE395_EI01_ONLY_OVERLAY_BUILD_PASS")
    print("net_electron_stoich=-1")
    print("electron_energy_loss_eV=0")
    print("oxygen_nuclei_closure=-2+1+1=0")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
