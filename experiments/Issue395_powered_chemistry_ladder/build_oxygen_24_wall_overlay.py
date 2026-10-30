#!/usr/bin/env python3
"""Add research-only gamma=1 neutral loss on six plasma solid walls.

This follows the Issue27 combined O/O2s/Os thermal-flux formulation.
DO NOT duplicate existing charged-ion or electron sheath wall laws.
The powered input must independently certify charged wall coefficients.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

WALLS=("plasma_electrode","plasma_metal","plasma_right",
       "plasma_cover","plasma_wafer","plasma_focus_ring")
SPECIES={"O":("w_O",0.016),"O2s":("w_O2s",0.032),"Os":("w_Os",0.016)}
GAMMA=1.0
R_GAS=8.31446
PI=3.141592653589793
REQUIRED=("[w_O]","[w_O2s]","[w_Os]","property_name = rho_neutral","T_g")
# Check explicit charged coefficients in the prepared powered input.
# Existing ion wall source must NOT be replaced by a second, parallel source.
ION_MATERIAL_NAMES=("ion_wall_flux","negative_ion_wall_flux",
                    "atomic_positive_ion_wall_flux")
BLOCK=re.compile(r"(?ms)^  \[(?P<name>[^\]\n]+)\][ \t]*\n(?P<body>.*?)^  \[\][ \t]*(?=\r?$)")
GAMMA_RE=re.compile(r"(?m)^[ \t]*sticking[ \t]*=[ \t]*([^\s#]+)")


def charged_wall_audit(input_text: str) -> dict[str,float]:
    blocks={}
    for match in BLOCK.finditer(input_text):
        blocks.setdefault(match.group("name"),[]).append(match.group("body"))
    verified={}
    for name in ION_MATERIAL_NAMES:
        found=blocks.get(name,[])
        if len(found)!=1:
            raise ValueError(f"charged wall flux {name} must occur exactly once, found {len(found)}")
        body=found[0]
        if "type = PhysicsIonWallFluxMaterial" not in body and \
           "type = PhysicsIonWallTotalFluxMaterial" not in body:
            raise ValueError(f"{name}: unexpected charged wall material type")
        gamma=GAMMA_RE.search(body)
        if gamma is None or float(gamma.group(1))!=1.0:
            raise ValueError(f"{name}: existing charged sticking must be exactly 1.0")
        verified[name]=float(gamma.group(1))
    # The electron sheath is a separate wall law; not a neutral sticking source.
    if "electron_wall_number_flux" not in input_text:
        raise ValueError("missing powered electron sheath wall closure")
    return verified


def build(base: str, *, require_charged_wall_audit:bool=True) -> str:
    for token in REQUIRED:
        if token not in base:
            raise ValueError(f"prepared powered input missing {token}")
    for forbidden in ("chem24_wall_O","chem24_wall_O2s","chem24_wall_Os"):
        if forbidden in base:
            raise ValueError(f"existing duplicate research wall object: {forbidden}")
    if require_charged_wall_audit:
        charged_wall_audit(base)
    boundaries="'"+' '.join(WALLS)+"'"
    materials=[]; bcs=[]; monitors=[]
    for name,(variable,molar_mass) in SPECIES.items():
        functor=f"chem24_wall_{name}_mass_flux"
        mats=f"""  [chem24_wall_{name}_material]
    type = ADParsedFunctorMaterial
    property_name = {functor}
    functor_names = 'rho_neutral {variable} T_g'
    functor_symbols = 'rho y tg'
    expression = '0.25*sqrt(8.0*{R_GAS:.17g}*tg/({PI:.17g}*{molar_mass:.17g}))*rho*y'
    block = plasma
  []"""
        bc=f"""  [chem24_wall_{name}_sink]
    type = FVFunctorNeumannBC
    variable = {variable}
    boundary = {boundaries}
    functor = {functor}
    factor = -1.0
  []"""
        pp=f"""  [chem24_wall_{name}_mass_loss]
    type = SideFVFluxBCIntegral
    boundary = {boundaries}
    fvbcs = 'chem24_wall_{name}_sink'
    execute_on = 'INITIAL TIMESTEP_END'
  []"""
        materials.append(mats);bcs.append(bc);monitors.append(pp)
    return ("# Research wall model: neutral O, O2(a), O(1D) gamma=1, Motz-Wise off.\n"
            "# No additional ion or electron wall flux; use existing powered laws.\n"
            "[FunctorMaterials]\n"+"\n".join(materials)+"\n[]\n"
            "[FVBCs]\n"+"\n".join(bcs)+"\n[]\n"
            "[Postprocessors]\n"+"\n".join(monitors)+"\n[]\n")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--base-input",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    if a.output.resolve()==a.base_input.resolve():
        raise ValueError("cannot overwrite source input")
    text=a.base_input.read_text()
    audit=charged_wall_audit(text)
    wall=build(text,require_charged_wall_audit=False)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(wall)
    print("OXYGEN_24_SIX_WALL_STICKING1_PREPARED_NOT_RUN")
    print("charged_wall_coefficients",audit)


if __name__=="__main__":
    main()
