#!/usr/bin/env python3
"""Create ONE research-only 24-reaction oxygen ICP source overlay.

Inventory: 19 independently tabulated electron-impact reactions (EI-936 OUT),
2 electron-rate formulae (EI-2259, EI-2738), 3 heavy-rate formulae (H23-H25).
Produces a .i fragment; never represents a successful MOOSE time integration.
Run this instead of the old individual chemistry overlays, not alongside them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
from collections import Counter
from pathlib import Path

N_A = 6.02214076e23
M = {"O2": 0.032, "O2a": 0.032, "O2p": 0.032,
     "O": 0.016, "Os": 0.016, "Op": 0.016, "Om": 0.016}
CHARGE = {"e": -1, "O2p": 1, "Op": 1, "Om": -1}
ATOMS = {"O2":2, "O2a":2, "O2p":2, "O":1, "Os":1, "Op":1, "Om":1}
HEAVY = tuple(M)
NEUTRALS = ("O2", "O2a", "O", "Os")
ION_LOG = {"O2p": "log_ni", "Op": "log_nop", "Om": "log_nm"}
FRACTIONS = {"O2":"w_O2_constraint", "O2a":"w_O2s", "O":"w_O", "Os":"w_Os"}
PARENT = {
    401:"O2",407:"O2",411:"O2",412:"O2",413:"O2",414:"O2",
    415:"O2",417:"O2",2058:"O2a",2067:"O2a",2068:"O2a",
    2069:"O2a",2072:"O2a",2073:"O2a",2074:"O2a",
    935:"O",941:"O",943:"Os",944:"Os"}
# Electron energy eV/event: effective losses (negative = superelastic gain).
LOSS = {401:0.,407:.977,411:4.5,412:6.,413:8.4,414:10.,
        415:12.06,417:17.,2058:3.5,2067:-.977,2068:3.52,
        2069:5.02,2072:11.08,2073:13.72,2074:16.023,
        935:1.97,941:13.62,943:-1.97,944:11.65,2738:2.70}
# Net stoichiometry includes electrons; O2a maps to MOOSE O2s, Os maps O(1D).
CHEM = {
    401:{"e":-1,"O2":-1,"Om":1,"O":1},
    407:{"O2":-1,"O2a":1},
    411:{"O2":-1,"O":2},
    412:{"O2":-1,"O":2},
    413:{"O2":-1,"O2a":1},
    414:{"O2":-1,"O2a":1},
    415:{"e":1,"O2":-1,"O2p":1},
    417:{"e":1,"O2":-1,"Op":1,"O":1},
    2058:{"e":-1,"O2a":-1,"Om":1,"O":1},
    2067:{"O2a":-1,"O2":1},
    2068:{"O2a":-1,"O":2},
    2069:{"O2a":-1,"O":2},
    2072:{"e":1,"O2a":-1,"O2p":1},
    2073:{"O2a":-1,"O":2},
    2074:{"e":1,"O2a":-1,"Op":1,"O":1},
    935:{"O":-1,"Os":1},
    941:{"e":1,"O":-1,"Op":1},
    943:{"Os":-1,"O":1},
    944:{"e":1,"Os":-1,"Op":1},
    2259:{"e":-1,"O2p":-1,"O":2},
    2738:{"e":1,"Om":-1,"O":1},
    "H23":{"Op":-1,"Om":-1,"O":2},
    "H24":{"Om":-1,"O2p":-1,"O2":1,"O":1},
    "H25":{"Op":-1,"O2":-1,"O":1,"O2p":1},
}
LOOKUP_IDS = tuple(PARENT)
FORMULA_IDS = (2259,2738)
HEAVY_IDS = ("H23","H24","H25")
REQUIRED = (
    "[log_ne]", "[log_ni]", "[log_nm]", "[log_nop]",
    "[log_energy]", "[w_O2s]", "[w_O]", "[w_Os]", "[p]",
    "property_name = w_O2_constraint", "property_name = rho_neutral",
    "property_name = n_e_physical", "mean_energy = mean_en_solved"
)
FORBIDDEN = (
    "R_attachment", "R_diss_O2", "R_ion_O2", "R_ion_O", "R_O2s",
    "R_EI407", "R_EI2738", "R_EI2259",
)
ROWS = 100

def validate_network() -> dict:
    if len(CHEM) != 24 or len(LOOKUP_IDS) != 19:
        raise ValueError("incorrect 24=19+2+3 reaction census")
    if set(CHEM) != set(LOOKUP_IDS) | set(FORMULA_IDS) | set(HEAVY_IDS):
        raise ValueError("rate owner and stoichiometry mismatch")
    for rid, delta in CHEM.items():
        if sum(n*ATOMS.get(sp, 0) for sp,n in delta.items()) != 0:
            raise ValueError(f"{rid}: oxygen atoms not conserved")
        if sum(n*CHARGE.get(sp, 0) for sp,n in delta.items()) != 0:
            raise ValueError(f"{rid}: charge not conserved")
        if sum(n*M.get(sp, 0) for sp,n in delta.items()) != 0:
            raise ValueError(f"{rid}: heavy mass not conserved")
    if 936 in CHEM:
        raise ValueError("EI-936 explicitly excluded")
    return {"active":24, "lookups":19, "formula":2, "heavy":3,
            "atoms_charge_mass":"PASS", "original_25_registry":"UNCHANGED"}

def validate_table(path: Path) -> list[tuple[float,float]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    result=[]
    for raw in path.read_text().splitlines():
        raw=raw.split("#",1)[0].strip()
        if not raw: continue
        parts=raw.split()
        if len(parts)!=2: raise ValueError(f"{path}: requires two columns")
        e,k=map(float,parts)
        if not (math.isfinite(e) and math.isfinite(k) and e>0 and k>=0):
            raise ValueError(f"{path}: invalid point")
        if result and e<=result[-1][0]:
            raise ValueError(f"{path}: non-increasing mean-energy grid")
        result.append((e,k))
    if len(result)!=ROWS: raise ValueError(f"{path}: expected {ROWS} rows")
    return result

def validate_files(folder: Path) -> dict[int,Path]:
    paths={}
    grid=None
    for rid,parent in PARENT.items():
        target={"O2":"O2_X","O2a":"O2_a1Delta","O":"O_3P","Os":"O_1D"}[parent]
        file=folder/f"EI-{rid}_{target}.txt"
        points=validate_table(file)
        if grid is None: grid=[p[0] for p in points]
        if any(not math.isclose(a,p[0],rel_tol=1e-10,abs_tol=1e-10)
               for a,p in zip(grid,points)):
            raise ValueError(f"{rid}: rate mean-energy grid mismatch")
        paths[rid]=file
    return paths

def material(name, ptype, *parameters):
    return "\n".join([f"  [{name}]",f"    type = {ptype}"]+
                     [f"    {k} = {v}" for k,v in parameters]+["    block = plasma","  []"])

def parsed(name, output, functors, symbols, expression):
    if not functors or len(functors)!=len(symbols):
        raise ValueError("bad parsed expression")
    return material(name,"ADParsedFunctorMaterial",
        ("property_name",output),
        ("functor_names","'"+' '.join(functors)+"'"),
        ("functor_symbols","'"+' '.join(symbols)+"'"),
        ("expression","'"+expression+"'"))

def sum_functor(name, terms):
    if not terms: raise ValueError(name)
    symbols=[f"q{i}" for i in range(len(terms))]
    # Group by reaction progress: no reaction is interpolated more than once.
    return parsed("chem24_"+name, name, [f"R_{i}" for i,v in terms],
                  symbols, "+".join(f"({v:.17g})*{s}" for s,(_,v) in zip(symbols,terms)))

def make_overlay(paths: dict[int,str], baseline: str) -> str:
    validate_network()
    missing=[v for v in REQUIRED if v not in baseline]
    inherited=[v for v in FORBIDDEN if v in baseline]
    if missing or inherited:
        raise ValueError(f"refuse invalid baseline missing={missing} inherited={inherited}")
    if set(paths)!=set(LOOKUP_IDS):
        raise ValueError("all 19 unique electron-impact tables required")
    material_blocks=[]
    for sp in NEUTRALS:
        material_blocks.append(parsed(f"chem24_target_{sp}",f"c_chem24_{sp}",
            ["rho_neutral",FRACTIONS[sp]],["rho","w"],
            f"rho*w/{M[sp]:.17g}"))
    for sp,var in ION_LOG.items():
        material_blocks.append(parsed(f"chem24_target_{sp}",f"c_chem24_{sp}",
            [var],["lnc"],"exp(lnc)"))
    material_blocks.append(parsed("chem24_temperature","Te_chem24_eV",
        ["mean_en_solved"],["eps"],"(2.0/3.0)*eps"))
    for rid,parent in PARENT.items():
        filename=paths[rid]
        if "'" in filename or "\n" in filename: raise ValueError("unsafe rate path")
        material_blocks.append(material(f"chem24_rate_{rid}","PhysicsElectronImpactRateMaterial",
            ("rate_table_file",f"'{filename}'"),
            ("mean_energy","mean_en_solved"),
            ("electron_number_density","n_e_physical"),
            ("target_molar_concentration",f"c_chem24_{parent}"),
            ("reaction_progress",f"R_{rid}")))
    # Formula molar progress: n_e[1/m3]*c_target[mol/m3]*k[m3/s].
    material_blocks.append(parsed("chem24_rate_2259","R_2259",
        ["n_e_physical","c_chem24_O2p","Te_chem24_eV"],["ne","c","te"],
        "2.4e-13*(300.0/(te*11604.51812155))^0.70*ne*c"))
    material_blocks.append(parsed("chem24_rate_2738","R_2738",
        ["n_e_physical","c_chem24_Om","Te_chem24_eV"],["ne","c","te"],
        "2.0e-13*exp(-5.5/te)*ne*c"))
    # Convert particle-basis m^3/s to molar progress using Avogadro ONCE.
    for rid,reactants,a in (("H23",("Op","Om"),1e-13),
                            ("H24",("Om","O2p"),1e-13)):
        material_blocks.append(parsed(f"chem24_rate_{rid}",f"R_{rid}",
            [f"c_chem24_{sp}" for sp in reactants],["a","b"],
            f"{a*N_A:.17g}*a*b"))
    material_blocks.append(parsed("chem24_rate_H25","R_H25",
        ["c_chem24_Op","c_chem24_O2","T_g"],["a","b","t"],
        f"{2e-17*N_A:.17g}*(300.0/t)^0.4*a*b"))
    net={sp:[] for sp in ("e",)+HEAVY}
    for rid,sto in CHEM.items():
        for sp,coef in sto.items():
            net[sp].append((rid,coef))
    # The constrained O2 channel is source closure only; NEVER a second O2 kernel.
    for sp,terms in net.items():
        material_blocks.append(sum_functor(f"S_mol_{sp}",terms))
    for sp in HEAVY:
        material_blocks.append(parsed(f"chem24_mass_{sp}",f"S_mass_{sp}",
            [f"S_mol_{sp}"],["r"],f"{M[sp]:.17g}*r"))
    neutral_terms=[(sp,1.) for sp in NEUTRALS]
    material_blocks.append(parsed("chem24_pressure_mass","S_neutral_mass_chem24",
        [f"S_mass_{sp}" for sp in NEUTRALS],
        ["a","b","c","d"],"a+b+c+d"))
    # Energy is one combined term, negative gains become a positive source.
    losses=[(rid,-v) for rid,v in LOSS.items() if v!=0.]
    material_blocks.append(sum_functor("S_energy_chem24",losses))
    material_blocks.append(parsed("chem24_mass_closure","S_mass_closure_chem24",
        [f"S_mass_{sp}" for sp in HEAVY],
        [f"x{i}" for i in range(len(HEAVY))],
        "+".join(f"x{i}" for i in range(len(HEAVY)))))
    material_blocks.append(parsed("chem24_charge_closure","S_charge_closure_chem24",
        ["S_mol_e","S_mol_O2p","S_mol_Op","S_mol_Om"],
        ["e","o2p","op","om"],"-e+o2p+op-om"))
    kernels=[]
    for var,src in (("log_ne","S_mol_e"),("log_energy","S_energy_chem24")):
        kernels.append(material(f"chem24_source_{var}","FunctorKernel",
            ("variable",var),("functor",src),("functor_on_rhs","true")))
    fv=[]
    for sp,var in (("O2a","w_O2s"),("O","w_O"),("Os","w_Os")):
        fv.append(material(f"chem24_source_{sp}","PhysicsFVSpeciesReactionSource",
            ("variable",var),("source",f"S_mass_{sp}")))
    for sp,var in ION_LOG.items():
        fv.append(material(f"chem24_source_{sp}","FVCoupledForce",
            ("variable",var),("v",f"S_mol_{sp}"),("coef","1.0")))
    fv.append(material("chem24_neutral_pressure","FVCoupledForce",
        ("variable","p"),("v","S_neutral_mass_chem24"),("coef","1.0")))
    # Four tracked neutral species, number density [1/m3] from c [mol/m3].
    for sp,label in (("O2","n_O2_X_avg"),("O2a","n_O2_a_avg"),
                     ("O","n_O_3P_avg"),("Os","n_O_1D_avg")):
        material_blocks.append(parsed(f"chem24_density_{sp}",f"n_chem24_{sp}",
            [f"c_chem24_{sp}"],["c"],f"{N_A:.17g}*c"))
    pp=[]
    for sp,label in (("O2","n_O2_X_avg"),("O2a","n_O2_a_avg"),
                     ("O","n_O_3P_avg"),("Os","n_O_1D_avg")):
        pp.append(material(label,"ElementAverageFunctorPostprocessor",
            ("functor",f"n_chem24_{sp}"),("execute_on","'INITIAL TIMESTEP_END'")))
    for label in [f"R_{rid}" for rid in CHEM]+[
        "S_mass_closure_chem24","S_charge_closure_chem24",
        "S_energy_chem24","S_mol_O","S_mol_O2a","S_mol_Os"]:
        pp.append(material("chem24_monitor_"+label,"ElementAverageFunctorPostprocessor",
                           ("functor",label),("execute_on","'INITIAL TIMESTEP_END'")))
    return ("\n# SCIENTIFIC STATUS: user-selected reduced 24-channel reaction model.\n"
            "# Exclude all old separate chemistry overlays to avoid rate double counting.\n"
            "# Only O2(X) is a constrained mass fraction, no direct O2 kernel.\n"
            "[FunctorMaterials]\n"+"\n".join(material_blocks)+"\n[]\n"
            "[Kernels]\n"+"\n".join(kernels)+"\n[]\n"
            "[FVKernels]\n"+"\n".join(fv)+"\n[]\n"
            "[Postprocessors]\n"+"\n".join(pp)+"\n[]\n"
            "[Outputs]\n  csv = true\n[]\n")

def stage(base:Path, rate_dir:Path, output:Path, root:Path) -> dict:
    root=root.resolve()
    base=base.resolve()
    output=output.resolve()
    if not output.is_relative_to(root):
        raise ValueError("output must be in MOOSE repository execution root")
    if base==output: raise ValueError("refuse overwriting baseline")
    files=validate_files(rate_dir)
    dest=output.parent / "private_rates"
    dest.mkdir(parents=True, exist_ok=True)
    mapping={}
    hashes={}
    for rid,src in files.items():
        target=dest/src.name
        if target.exists() and hashlib.sha256(target.read_bytes()).digest()!=hashlib.sha256(src.read_bytes()).digest():
            raise ValueError(f"conflicting private lookup {target}")
        if src.resolve()!=target.resolve(): shutil.copyfile(src,target)
        mapping[rid]=target.relative_to(root).as_posix()
        hashes[str(rid)]=hashlib.sha256(target.read_bytes()).hexdigest()
    result=make_overlay(mapping, base.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")
    report=validate_network()
    report.update({"lookup_sha256":hashes,"overlay":str(output),"run_status":"NOT_RUN",
                   "note":"overlay only; verify physics-opt --check-input and bounded time integration"})
    (output.parent/"chem24_manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base-input",required=True,type=Path)
    p.add_argument("--rate-dir",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--root",required=True,type=Path)
    a=p.parse_args()
    report=stage(a.base_input,a.rate_dir,a.output,a.root)
    print("OXYGEN_24_CHEMISTRY_OVERLAY_PREPARED_NOT_RUN",json.dumps(report,sort_keys=True))

if __name__=="__main__":
    main()
