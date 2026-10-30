#!/usr/bin/env python3
"""Research-only EI-2738 thermal formula owner and source projector.

e + O- -> O(3P) + 2 e
k = 2.0e-13 exp(-5.5/Te_eV) m3/s, Te_eV=2/3 mean electron energy.
Published model reaction in Chinese Physics B 24 (2015) 095203, Table 1
and Plasma Science Technology 26 (2024) 125401, Table 1.
This is a temperature-fit rate, NOT a computed EEDF cross-section lookup.

R [mol/m3/s] = k[m3/s] n_e[1/m3] c_O-[mol/m3].
The existing log_nm state is ln(c_O- [mol/m3]) in this ICP model.
Historical 2.70 eV loss retained as an explicit approximate energy sink.
Not a substitute for a full powered 24-reaction ICP transient.
"""
from __future__ import annotations
import argparse
from pathlib import Path

RATE_PREF_M3_S = 2.0e-13
TE_EXP_EV = 5.5
ENERGY_LOSS_EV = 2.70
M_O_KG_MOL = 0.016
REQUIRED = ("[log_nm]", "[log_ne]", "[log_energy]", "[w_O]", "[p]",
            "property_name = n_e_physical", "mean_energy = mean_en_solved")
FORBIDDEN = ("R_EI2738", "S_O_mass_EI2738", "S_energy_EI2738",
             "[ei2738_detachment_progress]")


def build(base: str) -> str:
    missing = [token for token in REQUIRED if token not in base]
    duplicates = [token for token in FORBIDDEN if token in base]
    if missing or duplicates:
        raise ValueError(f"EI-2738 fail closed missing={missing} duplicate={duplicates}")
    return """# EI-2738 research-only: e+O- -> 2e+O(3P)
# Te=2/3 mean electron energy; no sigma(E) acquisition assumed.
[FunctorMaterials]
  [ei2738_temperature]
    type = ADParsedFunctorMaterial
    property_name = Te_EI2738_eV
    functor_names = 'mean_en_solved'
    functor_symbols = 'eps'
    expression = '(2.0/3.0)*eps'
    block = plasma
  []
  [ei2738_negative_ion_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_Om_EI2738
    functor_names = 'log_nm'
    functor_symbols = 'lnc'
    expression = 'exp(lnc)'
    block = plasma
  []
  [ei2738_rate_coefficient]
    type = ADParsedFunctorMaterial
    property_name = k_EI2738
    functor_names = 'Te_EI2738_eV'
    functor_symbols = 'te'
    expression = '2.0e-13*exp(-5.5/te)'
    block = plasma
  []
  [ei2738_detachment_progress]
    type = ADParsedFunctorMaterial
    property_name = R_EI2738
    functor_names = 'k_EI2738 n_e_physical c_Om_EI2738'
    functor_symbols = 'k ne c'
    expression = 'k*ne*c'
    block = plasma
  []
  [ei2738_electron_source]
    type = ADParsedFunctorMaterial
    property_name = S_e_molar_EI2738
    functor_names = 'R_EI2738'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [ei2738_om_source]
    type = ADParsedFunctorMaterial
    property_name = S_Om_molar_EI2738
    functor_names = 'R_EI2738'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [ei2738_o_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI2738
    functor_names = 'R_EI2738'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [ei2738_om_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Om_mass_EI2738
    functor_names = 'R_EI2738'
    functor_symbols = 'R'
    expression = '-0.016*R'
    block = plasma
  []
  [ei2738_neutral_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_EI2738
    functor_names = 'R_EI2738'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [ei2738_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_EI2738
    functor_names = 'S_O_mass_EI2738 S_Om_mass_EI2738'
    functor_symbols = 'a b'
    expression = 'a+b'
    block = plasma
  []
  [ei2738_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_closure_EI2738
    functor_names = 'S_e_molar_EI2738 S_Om_molar_EI2738'
    functor_symbols = 'e om'
    expression = 'e+om'
    block = plasma
  []
  [ei2738_energy_sink]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI2738
    functor_names = 'R_EI2738'
    functor_symbols = 'R'
    expression = '-2.70*R'
    block = plasma
  []
[]
[Kernels]
  [ei2738_electron_source_kernel]
    type = FunctorKernel
    variable = log_ne
    functor = S_e_molar_EI2738
    functor_on_rhs = true
    block = plasma
  []
  [ei2738_energy_sink_kernel]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI2738
    functor_on_rhs = true
    block = plasma
  []
[]
[FVKernels]
  [ei2738_negative_ion_sink]
    type = FVCoupledForce
    variable = log_nm
    v = S_Om_molar_EI2738
    coef = 1.0
    block = plasma
  []
  [ei2738_atomic_oxygen_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI2738
    block = plasma
  []
  [ei2738_neutral_mass_source_kernel]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_EI2738
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [ei2738_rate_avg]
    type = ElementAverageFunctorPostprocessor
    functor = R_EI2738
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2738_heavy_mass_closure_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_heavy_mass_closure_EI2738
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2738_charge_closure_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_charge_closure_EI2738
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--base-input",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.base_input.resolve() == args.output.resolve():
        raise ValueError("do not replace baseline input")
    out=build(args.base_input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(out,encoding="utf-8")
    print("EI2738_FORMULA_OVERLAY_GENERATED_NOT_POWERED_RUN")


if __name__=="__main__":
    main()
