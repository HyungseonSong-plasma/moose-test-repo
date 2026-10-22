#!/usr/bin/env python3
"""Build Issue #395 EI20-only atomic-O ionization overlay.

Reaction: e + O -> 2e + O+

This overlay is intentionally limited to EI20 so it can be composed with the
existing EI02 elastic, O2 dissociation, and EI16 O2 ionization overlays without
activating any other Stage-5 chemistry channel.
"""
from __future__ import annotations

import argparse
from pathlib import Path

M_O = 0.016
EI20_LOSS_EV = 13.618


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--ei20-table", default="o_ionization.txt")
    a = p.parse_args()

    base = a.base_input.read_text(encoding="utf-8")
    required = (
        "property_name = n_e_physical",
        "mean_energy = mean_en_solved",
        "property_name = rho_neutral",
        "[w_O]",
        "[log_nop]",
        "[log_ne]",
        "[log_energy]",
        "[p]",
    )
    missing = [x for x in required if x not in base]
    if missing:
        raise RuntimeError(f"EI20 base-input capability audit failed; missing {missing}")
    if "R_ion_O" in base:
        raise RuntimeError("EI20 requires no inherited atomic-O ionization owner")

    text = f'''# Issue #395: EI20 atomic-O ionization only
# Reaction: e + O -> 2e + O+
# One canonical progress owner: R_ion_O [mol/(m^3 s)]
# Net electron source: +1 electron/event
# Electron-energy loss: {EI20_LOSS_EV:.17g} eV/event

[FunctorMaterials]
  [ei20_o_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O_EI20
    functor_names = 'rho_neutral w_O'
    functor_symbols = 'rho w'
    expression = 'rho*w/{M_O:.17g}'
    block = plasma
  []
  [ei20_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = {a.ei20_table}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O_EI20
    reaction_progress = R_ion_O
    block = plasma
  []
  [ei20_electron_source]
    type = ADParsedFunctorMaterial
    property_name = S_electron_molar_EI20
    functor_names = 'R_ion_O'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [ei20_op_source]
    type = ADParsedFunctorMaterial
    property_name = S_Op_molar_EI20
    functor_names = 'R_ion_O'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [ei20_o_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI20
    functor_names = 'R_ion_O'
    functor_symbols = 'R'
    expression = '-{M_O:.17g}*R'
    block = plasma
  []
  [ei20_neutral_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_EI20
    functor_names = 'R_ion_O'
    functor_symbols = 'R'
    expression = '-{M_O:.17g}*R'
    block = plasma
  []
  [ei20_op_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_Op_mass_EI20
    functor_names = 'R_ion_O'
    functor_symbols = 'R'
    expression = '{M_O:.17g}*R'
    block = plasma
  []
  [ei20_energy_source]
    type = ADParsedFunctorMaterial
    property_name = S_electron_energy_molar_EI20
    functor_names = 'R_ion_O'
    functor_symbols = 'R'
    expression = '-{EI20_LOSS_EV:.17g}*R'
    block = plasma
  []
  [ei20_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_EI20
    functor_names = 'S_neutral_mass_EI20 S_Op_mass_EI20'
    functor_symbols = 'Sn Si'
    expression = 'Sn+Si'
    block = plasma
  []
  [ei20_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_molar_closure_EI20
    functor_names = 'S_electron_molar_EI20 S_Op_molar_EI20'
    functor_symbols = 'Se Si'
    expression = 'Si-Se'
    block = plasma
  []
[]

[Kernels]
  [ei20_electron_particle_source]
    type = FunctorKernel
    variable = log_ne
    functor = S_electron_molar_EI20
    functor_on_rhs = true
    block = plasma
  []
  [ei20_electron_energy_source]
    type = FunctorKernel
    variable = log_energy
    functor = S_electron_energy_molar_EI20
    functor_on_rhs = true
    block = plasma
  []
[]

[FVKernels]
  [ei20_atomic_oxygen_sink]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI20
    block = plasma
  []
  [ei20_neutral_mass_sink]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_EI20
    coef = 1.0
    block = plasma
  []
  [ei20_atomic_positive_ion_source]
    type = FVCoupledForce
    variable = log_nop
    v = S_Op_molar_EI20
    coef = 1.0
    block = plasma
  []
[]

[Postprocessors]
  [ei20_R_ion_O_min]
    type = ADElementExtremeFunctorValue
    functor = R_ion_O
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei20_R_ion_O_max]
    type = ADElementExtremeFunctorValue
    functor = R_ion_O
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei20_R_ion_O_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_ion_O
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei20_energy_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_electron_energy_molar_EI20
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei20_O_mass_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O_mass_EI20
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei20_Op_mass_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_Op_mass_EI20
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei20_electron_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_electron_molar_EI20
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei20_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_EI20
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei20_charge_molar_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_molar_closure_EI20
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
'''

    a.output.write_text(text, encoding="utf-8")
    print("ISSUE395_EI20_ONLY_OVERLAY_BUILD_PASS")
    print(f"loss_eV_per_event={EI20_LOSS_EV:.17g}")
    print(f"output={a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
