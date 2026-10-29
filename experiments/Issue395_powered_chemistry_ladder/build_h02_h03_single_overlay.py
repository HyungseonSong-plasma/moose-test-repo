#!/usr/bin/env python3
"""Strict one-arm oxygen heavy-ion neutralization overlay for active B case.

H02: O- + O+  -> 2 O(3P), k = 4.0e-14*(300/Tg)^0.43 m3/s.
H03: O- + O2+ -> 3 O(3P), k = 2.6e-14*(300/Tg)^0.44 m3/s.

Rate owner: ADParsedFunctorMaterial R_H02 or R_H03, mol/m3/s.
The pinned plasma model transports log_nm/log_nop/log_ni as log(mol/m3);
the heavy reaction is computed from the physically solved molar concentrations
exp(log_n*) and fixed heavy temperature T_g_fixed. For a bimolecular reaction,
R [mol/m3/s] = k_particle [m3/s] * NA * c_ion1*c_ion2.
PhysicsReactionRateMaterial in historical Stage5 instead consumes mass fractions
of a different heavy-mixture model; no blanket replacement is asserted.

Charge and O nuclei conserve exactly; electrons have no source/sink.
Charged-ion loss = neutral-O gain, with neutral pressure mass source separately.
No *electron* energy sink for a purely heavy-heavy reaction. Any reaction enthalpy
or excited product states remain science HOLD pending a heavy-energy model.
"""
from __future__ import annotations
import argparse
from pathlib import Path

NA=6.02214076e23
MO=0.016
MO2=0.032
CASES={
  "H02": {
    "k0":4.0e-14, "exp":0.43, "partner":"log_nop",
    "ionsink_mass":MO, "atomic_count":2,
    "reaction":"Om + Op -> O + O",
    "id":"H02_Om_Op_neutralization",
  },
  "H03": {
    "k0":2.6e-14, "exp":0.44, "partner":"log_ni",
    "ionsink_mass":MO2, "atomic_count":3,
    "reaction":"Om + O2p -> O + O + O",
    "id":"H03_Om_O2p_to_3O",
  }
}

def build(base: str, arm: str) -> str:
    d=CASES[arm]
    for token in ("[log_nm]", f"[{d['partner']}]", "[w_O]", "[p]",
                  "property_name = rho_neutral", "T_g_fixed",
                  "type = PhysicsFVLogMolarElectronTimeDerivative"):
        if token not in base:raise ValueError(f"Missing fixed baseline provider: {token}")
    if "R_H02" in base or "R_H03" in base:raise ValueError("inherited heavy rate owner")
    r=f"R_{arm}"
    total=MO*d["atomic_count"]
    if abs(total-(MO+d["ionsink_mass"]))>1e-14:
        raise AssertionError("mass conservation")
    return f"""# Isolated {arm} heavy-heavy reaction, only arm enabled in this overlay.
# Source: physics_app/data/heavy_reactions/stage5_s5d_oxygen_heavy.txt.
# {d['reaction']} ; {d['id']}
# k0={d['k0']:.17g} m3/s * (300/Tg)^{d['exp']:.17g}.
# Positive molar reaction rate; electron-number projection ZERO.
# No electron impact; omitted heavy energy release is a science-HOLD boundary.
[FunctorMaterials]
  [{arm.lower()}_progress]
    type = ADParsedFunctorMaterial
    property_name = {r}
    functor_names = 'log_nm {d["partner"]} T_g_fixed'
    functor_symbols = 'lnm lnp tg'
    expression = '{d["k0"]*NA:.17g}*exp(lnm+lnp)*((300.0/tg)^{d["exp"]:.17g})'
    block = plasma
  []
  [{arm.lower()}_om_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Om_molar_{arm}
    functor_names = '{r}'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [{arm.lower()}_positive_ion_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Pos_molar_{arm}
    functor_names = '{r}'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [{arm.lower()}_o_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_{arm}
    functor_names = '{r}'
    functor_symbols = 'R'
    expression = '{total:.17g}*R'
    block = plasma
  []
  [{arm.lower()}_neutral_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_{arm}
    functor_names = '{r}'
    functor_symbols = 'R'
    expression = '{total:.17g}*R'
    block = plasma
  []
  [{arm.lower()}_om_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Om_mass_{arm}
    functor_names = '{r}'
    functor_symbols = 'R'
    expression = '-{MO:.17g}*R'
    block = plasma
  []
  [{arm.lower()}_positive_ion_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Pos_mass_{arm}
    functor_names = '{r}'
    functor_symbols = 'R'
    expression = '-{d["ionsink_mass"]:.17g}*R'
    block = plasma
  []
  [{arm.lower()}_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_mass_closure_{arm}
    functor_names = 'S_O_mass_{arm} S_Om_mass_{arm} S_Pos_mass_{arm}'
    functor_symbols = 'So Som Sp'
    expression = 'So+Som+Sp'
    block = plasma
  []
  [{arm.lower()}_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_molar_closure_{arm}
    functor_names = 'S_Om_molar_{arm} S_Pos_molar_{arm}'
    functor_symbols = 'Som Sp'
    expression = 'Som-Sp'
    block = plasma
  []
[]

[FVKernels]
  [{arm.lower()}_om_number_sink]
    type = FVCoupledForce
    variable = log_nm
    v = S_Om_molar_{arm}
    coef = 1.0
    block = plasma
  []
  [{arm.lower()}_positive_number_sink]
    type = FVCoupledForce
    variable = {d["partner"]}
    v = S_Pos_molar_{arm}
    coef = 1.0
    block = plasma
  []
  [{arm.lower()}_o_mass_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_{arm}
    block = plasma
  []
  [{arm.lower()}_neutral_mass_source]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_{arm}
    coef = 1.0
    block = plasma
  []
[]

[Postprocessors]
  [{arm.lower()}_R_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = {r}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [{arm.lower()}_om_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_Om_molar_{arm}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [{arm.lower()}_positive_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_Pos_molar_{arm}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [{arm.lower()}_o_mass_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O_mass_{arm}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [{arm.lower()}_neutral_mass_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_{arm}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [{arm.lower()}_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_mass_closure_{arm}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [{arm.lower()}_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_molar_closure_{arm}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base-input",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--arm",required=True,choices=("H02","H03"))
    a=p.parse_args()
    text=build(a.base_input.read_text(),a.arm)
    assert text.count("    property_name = R_"+a.arm+"\n")==1
    assert "    property_name = R_"+("H03" if a.arm=="H02" else "H02")+"\n" not in text
    assert text.count("    variable = log_nm\n")==1
    assert text.count("    variable = "+CASES[a.arm]["partner"]+"\n")==1
    assert "variable = log_energy" not in text
    a.output.write_text(text)
    print("ISSUE395_"+a.arm+"_EXCLUSIVE_HEAVY_ION_REACTION_PASS")

if __name__=="__main__":
    main()
