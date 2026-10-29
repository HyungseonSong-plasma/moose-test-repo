#!/usr/bin/env python3
"""Bounded EDETACH_OM overlay for Issue395 oxygen ICP 1000W discriminator.

Source: docs/development/2026-09-10_issue176_stage5_s5c_edetach_contract.json
e + O- -> O + 2e. Net one e produced; the explicit 12 eV/event sink
is the frozen chemistry model convention, not claimed cross-section parity.
"""
from __future__ import annotations
import argparse
import pathlib

K0 = 5.47e-14  # m^3/s
EA = 2.98      # eV, fit parameter
TE_EXP = 0.324
LOSS = 12.0    # eV/event
MO = 0.016     # kg/mol

def build(base: str) -> str:
    required = (
        "[log_ne]", "[log_nm]", "[log_energy]", "[w_O]", "[p]",
        "property_name = n_e_physical",
        "property_name = negative_ion_molar_density",
        "mean_energy = mean_en_solved",
        "property_name = rho_neutral",
    )
    missing = [token for token in required if token not in base]
    if missing:
        raise RuntimeError("EDETACH base-input capability mismatch: " + repr(missing))
    if any(t in base for t in ("R_detach_Om", "S_electron_molar_EDETACH")):
        raise RuntimeError("Existing EDETACH owner; duplicate is forbidden")
    return f"""# EDETACH_OM, frozen source-backed analytic model; SCIENCE HOLD
# e + O- -> O + 2e; net +1 electron, -1 O-, +1 O(3P)
# k = {K0:.17g} * exp(-{EA:.17g}/Te_eV) * Te_eV^{TE_EXP:.17g} [m^3/s]
# Electron-energy loss = {LOSS:.17g} eV/event
[FunctorMaterials]
  [edetach_electron_temperature]
    type = ADParsedFunctorMaterial
    property_name = Te_EDETACH_eV
    functor_names = 'mean_en_solved'
    functor_symbols = 'eps'
    expression = '(2.0/3.0)*eps'
    block = plasma
  []
  [edetach_progress]
    type = ADParsedFunctorMaterial
    property_name = R_detach_Om
    functor_names = 'n_e_physical negative_ion_molar_density Te_EDETACH_eV'
    functor_symbols = 'ne com te'
    expression = '{K0:.17g}*ne*com*exp(-{EA:.17g}/te)*(te^{TE_EXP:.17g})'
    block = plasma
  []
  [edetach_electron_molar_source]
    type = ADParsedFunctorMaterial
    property_name = S_electron_molar_EDETACH
    functor_names = 'R_detach_Om'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [edetach_om_molar_source]
    type = ADParsedFunctorMaterial
    property_name = S_Om_molar_EDETACH
    functor_names = 'R_detach_Om'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [edetach_om_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_Om_mass_EDETACH
    functor_names = 'R_detach_Om'
    functor_symbols = 'R'
    expression = '-{MO:.17g}*R'
    block = plasma
  []
  [edetach_o_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EDETACH
    functor_names = 'R_detach_Om'
    functor_symbols = 'R'
    expression = '{MO:.17g}*R'
    block = plasma
  []
  [edetach_neutral_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_EDETACH
    functor_names = 'R_detach_Om'
    functor_symbols = 'R'
    expression = '{MO:.17g}*R'
    block = plasma
  []
  [edetach_electron_energy_sink]
    type = ADParsedFunctorMaterial
    property_name = S_electron_energy_molar_EDETACH
    functor_names = 'R_detach_Om'
    functor_symbols = 'R'
    expression = '-{LOSS:.17g}*R'
    block = plasma
  []
  [edetach_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_EDETACH
    functor_names = 'S_Om_mass_EDETACH S_O_mass_EDETACH'
    functor_symbols = 'Sm So'
    expression = 'Sm+So'
    block = plasma
  []
  [edetach_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_molar_closure_EDETACH
    functor_names = 'S_electron_molar_EDETACH S_Om_molar_EDETACH'
    functor_symbols = 'Se Sm'
    expression = 'Se+Sm'
    block = plasma
  []
[]

[Kernels]
  [edetach_electron_source]
    type = FunctorKernel
    variable = log_ne
    functor = S_electron_molar_EDETACH
    functor_on_rhs = true
    block = plasma
  []
  [edetach_electron_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_electron_energy_molar_EDETACH
    functor_on_rhs = true
    block = plasma
  []
[]

[FVKernels]
  [edetach_negative_ion_sink]
    type = FVCoupledForce
    variable = log_nm
    v = S_Om_molar_EDETACH
    coef = 1.0
    block = plasma
  []
  [edetach_atomic_oxygen_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EDETACH
    block = plasma
  []
  [edetach_neutral_mass_source]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_EDETACH
    coef = 1.0
    block = plasma
  []
[]

[Postprocessors]
  [edetach_R_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_detach_Om
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [edetach_electron_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_electron_molar_EDETACH
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [edetach_om_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_Om_molar_EDETACH
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [edetach_o_mass_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O_mass_EDETACH
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [edetach_neutral_mass_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_EDETACH
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [edetach_energy_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_electron_energy_molar_EDETACH
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [edetach_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_EDETACH
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [edetach_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_molar_closure_EDETACH
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-input", type=pathlib.Path, required=True)
    p.add_argument("--output", type=pathlib.Path, required=True)
    a = p.parse_args()
    text = build(a.base_input.read_text())
    assert text.count("property_name = R_detach_Om") == 1
    assert text.count("variable = log_ne") == 1
    assert text.count("variable = log_nm") == 1
    assert text.count("variable = w_O") == 1
    assert text.count("variable = p") == 1
    a.output.write_text(text)
    print("ISSUE395_EDETACH_OM_EXCLUSIVE_SOURCE_PASS")

if __name__ == "__main__":
    main()
