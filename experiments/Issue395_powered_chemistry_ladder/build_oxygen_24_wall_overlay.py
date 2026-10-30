#!/usr/bin/env python3
"""Set gamma=1 in EXISTING Stage-B4 plasma wall materials (no duplicate BC).

The powered Issue397 base is materialized from the accepted Stage-B4
cover-pilot payload, which already has three neutral wall loss BCs.
Do not add a second overlapping surface sink. Preserve ion/electron
sheath BCs. Fail closed if the inherited wall layout has changed.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

WALLS=("plasma_electrode","plasma_metal","plasma_right",
       "plasma_cover","plasma_wafer","plasma_focus_ring")
SPECIES={"O":"w_O","O2s":"w_O2s","Os":"w_Os"}
NAME={s:f"stageb4_{s}_surface_flux" for s in SPECIES}
BC={s:f"stageb4_{s}_surface_loss" for s in SPECIES}
MATERIAL=re.compile(r"(?ms)^  \[(?P<name>[^\]\n]+)\][ \t]*\n(?P<body>.*?)^  \[\][ \t]*(?=\r?$)")
EXPRESSION=re.compile(r"(?m)^(?P<indent>[ \t]*expression[ \t]*=[ \t]*')(?P<gamma>[+0-9.eE-]+)(?P<tail>\*0\.25\*sqrt\([^\n']+'\s*)$")
WALL_BOUNDARY="'"+' '.join(WALLS)+"'"

def _wall_items(text:str)->dict[str,list[str]]:
    out={}
    for match in MATERIAL.finditer(text):
        out.setdefault(match.group("name"),[]).append(match.group("body"))
    return out

def inspect(base:str)->dict:
    blocks=_wall_items(base)
    for species,var in SPECIES.items():
        material=NAME[species]
        bc=BC[species]
        if len(blocks.get(material,[]))!=1 or len(blocks.get(bc,[]))!=1:
            raise ValueError(f"required existing Stage-B4 neutral wall pair missing/duplicated: {material}, {bc}")
        body=blocks[material][0]
        if f"property_name = stageb4_{species}_surface_mass_flux" not in body:
            raise ValueError(f"unexpected material owner for {material}")
        if f"{var}" not in body:
            raise ValueError(f"wrong neutral species {var} in {material}")
        if len(EXPRESSION.findall(body))!=1:
            raise ValueError(f"{material}: cannot uniquely locate existing sticking factor")
        bc_body=blocks[bc][0]
        if f"variable = {var}" not in bc_body:
            raise ValueError(f"{bc}: wrong species variable")
        if "type = FVFunctorNeumannBC" not in bc_body or "factor = -1.0" not in bc_body:
            raise ValueError(f"{bc}: unrecognized wall loss or sign")
        # No inlet/outlet allowed in the existing wall loss.
        if "inlet" in bc_body or "outlet" in bc_body:
            raise ValueError(f"{bc}: non-wall boundary included")
        for boundary in WALLS:
            if boundary not in bc_body:
                raise ValueError(f"{bc}: missing wall {boundary}")
    # Existing charged wall handling is independent; do not create second
    # ion BCs. Verify three charged wall flux owners and existing electron law.
    if not all(f in base for f in ("ion_wall_number_flux",
                                  "negative_ion_wall_number_flux",
                                  "atomic_positive_ion_wall_number_flux",
                                  "electron_wall_number_flux")):
        raise ValueError("missing charged/electron wall flux, cannot claim uniform wall law")
    # The three inherited charged species may use distinct material names.
    # Resolve them instead by signed charge and molar mass, not by name.
    ion_types=("PhysicsIonWallFluxMaterial","PhysicsIonWallTotalFluxMaterial")
    charged_expected={(1,0.032),(-1,0.016),(1,0.016)}
    charged_found={}
    for name,bodies in blocks.items():
        for body in bodies:
            if not any(f"type = {t}" in body for t in ion_types):
                continue
            def value(param):
                m=re.search(rf"(?m)^[ \\t]*{param}[ \\t]*=[ \\t]*([+-]?[0-9.eE+-]+)", body)
                if not m:raise ValueError(f"{name}: missing explicit numeric {param}")
                return float(m.group(1))
            charge=value("charge_number")
            mass=value("molar_mass")
            gamma=value("sticking")
            key=(round(charge),round(mass,3))
            if key not in charged_expected:
                continue
            if key in charged_found:raise ValueError(f"duplicate charged wall material for {key}")
            if gamma!=1.0:raise ValueError(f"{name}: sticking={gamma} is not 1.0")
            charged_found[key]=name
    if set(charged_found)!=charged_expected:
        raise ValueError(f"cannot verify all charged sticking=1.0: found {charged_found}")
    return {"neutral_walls":list(WALLS),
            "neutral_species":list(SPECIES),
            "charged_existing_fluxes":"present_not_overwritten",
            "charged_gamma_1_verified":sorted(charged_found.values())}

def apply(base:str)->str:
    inspect(base)
    # Replace coefficient only inside each exact Stage-B4 material block.
    def sub(match:re.Match)->str:
        name=match.group("name")
        body=match.group("body")
        if name not in NAME.values():
            return match.group(0)
        new,n=EXPRESSION.subn(lambda m:m.group("indent")+"1.0"+m.group("tail"),body,count=1)
        if n!=1:raise ValueError(f"cannot patch gamma for {name}")
        return f"  [{name}]\n{new}  []"
    updated=MATERIAL.sub(sub,base)
    inspected=_wall_items(updated)
    for s in SPECIES:
        body=inspected[NAME[s]][0]
        m=EXPRESSION.search(body)
        if not m or float(m.group("gamma"))!=1.0:
            raise ValueError(f"{s} sticking has not been set to 1")
    if any(new not in updated for new in ("stageb4_O_surface_loss",
                                         "stageb4_O2s_surface_loss","stageb4_Os_surface_loss")):
        raise ValueError("neutral wall sink lost")
    return updated

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--base-input",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    if args.output.resolve()==args.base_input.resolve():
        raise ValueError("do not overwrite input")
    src=args.base_input.read_text()
    updated=apply(src)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(updated)
    print("OXYGEN_24_NEUTRAL_EXISTING_WALL_GAMMA1_APPLIED")
    print("NO_NEW_WALL_BCS; 3 CHARGED STICKING=1.0 VERIFIED IN POWERED INPUT")

if __name__=="__main__":
    main()
