#!/usr/bin/env python3
"""B+H01 isolated oxygen charge transfer; benchmark against B and B+H02.

H01: O+ + O2(X) -> O(3P) + O2+
k = 2.0e-17*(300/T_g)^0.5 m3/s (particle basis),
historical stage5_s5d_oxygen_heavy.txt. Molar R=k*N_A*c_Op*c_O2.
H01 preserves oxygen nuclei, total mass and charge; neutral mass source
is -0.016*R, unlike H02's +0.032*R.
"""
from __future__ import annotations
import argparse
from pathlib import Path

NA=6.02214076e23
K0=2.0e-17
MO=0.016
MO2=0.032

def build(base: str) -> str:
    required=("[log_nop]","[log_ni]","[w_O]","[p]","w_O2_constraint",
              "property_name = rho_neutral","T_g_fixed",
              "type = PhysicsFVLogMolarElectronTimeDerivative")
    for token in required:
        if token not in base:raise AssertionError("Missing pinned baseline provider: "+token)
    if "R_H01" in base or "R_H02" in base or "R_H03" in base:
        raise AssertionError("Inherited heavy reaction progress already present")
    assert abs((-MO-MO2+MO+MO2))<1e-14
    return f"""# H01 ONLY: O+ + O2(X) -> O(3P) + O2+, frozen Stage5 rate fit.
# Particle rate k=2e-17*(300/T_g)^0.5 m3/s; rate stored mol/(m3 s).
# No electron particle or electron energy source; heavy energetics science HOLD.
[FunctorMaterials]
  [h01_o2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2_H01
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/0.032'
    block = plasma
  []
  [h01_progress]
    type = ADParsedFunctorMaterial
    property_name = R_H01
    functor_names = 'log_nop c_O2_H01 T_g_fixed'
    functor_symbols = 'lnp c2 tg'
    expression = '{K0*NA:.17g}*exp(lnp)*c2*((300.0/tg)^0.5)'
    block = plasma
  []
  [h01_op_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Op_molar_H01
    functor_names = 'R_H01'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [h01_o2p_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_molar_H01
    functor_names = 'R_H01'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [h01_o_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_H01
    functor_names = 'R_H01'
    functor_symbols = 'R'
    expression = '{MO:.17g}*R'
    block = plasma
  []
  [h01_o2_mass_sink_implicit]
    type = ADParsedFunctorMaterial
    property_name = S_O2_mass_H01_implicit
    functor_names = 'R_H01'
    functor_symbols = 'R'
    expression = '-{MO2:.17g}*R'
    block = plasma
  []
  [h01_neutral_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_H01
    functor_names = 'R_H01'
    functor_symbols = 'R'
    expression = '-{MO:.17g}*R'
    block = plasma
  []
  [h01_op_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Op_mass_H01
    functor_names = 'R_H01'
    functor_symbols = 'R'
    expression = '-{MO:.17g}*R'
    block = plasma
  []
  [h01_o2p_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_mass_H01
    functor_names = 'R_H01'
    functor_symbols = 'R'
    expression = '{MO2:.17g}*R'
    block = plasma
  []
  [h01_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_total_mass_closure_H01
    functor_names = 'S_O_mass_H01 S_O2_mass_H01_implicit S_Op_mass_H01 S_O2p_mass_H01'
    functor_symbols = 'so so2 sop so2p'
    expression = 'so+so2+sop+so2p'
    block = plasma
  []
  [h01_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_total_charge_closure_H01
    functor_names = 'S_Op_molar_H01 S_O2p_molar_H01'
    functor_symbols = 'op o2p'
    expression = 'op+o2p'
    block = plasma
  []
[]
[FVKernels]
  [h01_atomic_ion_sink]
    type = FVCoupledForce
    variable = log_nop
    v = S_Op_molar_H01
    coef = 1.0
    block = plasma
  []
  [h01_molecular_ion_source]
    type = FVCoupledForce
    variable = log_ni
    v = S_O2p_molar_H01
    coef = 1.0
    block = plasma
  []
  [h01_atomic_o_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_H01
    block = plasma
  []
  [h01_neutral_total_mass]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_H01
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [h01_R_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_H01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h01_op_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_Op_molar_H01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h01_o2p_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O2p_molar_H01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h01_o_mass_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O_mass_H01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h01_neutral_mass_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_H01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h01_o2_mass_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O2_mass_H01_implicit
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h01_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_total_mass_closure_H01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h01_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_total_charge_closure_H01
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--base-input",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    a=parser.parse_args()
    txt=build(a.base_input.read_text())
    if txt.count("    property_name = R_H01\n")!=1:raise AssertionError("rate owner not unique")
    if "    variable = log_nm\n" in txt or "    variable = log_ne\n" in txt:
        raise AssertionError("Incorrect electron or negative ion sink")
    a.output.write_text(txt)
    print("ISSUE395_H01_EXCLUSIVE_CHARGE_TRANSFER_OVERLAY_PASS")

if __name__=="__main__": main()
