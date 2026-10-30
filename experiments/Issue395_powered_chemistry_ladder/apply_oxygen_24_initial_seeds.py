#!/usr/bin/env python3
"""Set the user-approved charged initial densities for experimental O2 ICP.

Original physical species: electron=O2+=1e15/m3; O+=O-=1e12/m3.
The existing log_* state variable uses ln(c_molar [mol/m3]).
All other variable initial conditions, especially the neutral bulk, stay intact.
"""
from __future__ import annotations
import argparse
import math
import re
from pathlib import Path

N_A = 6.02214076e23
SEEDS_M3 = {"log_ne":1e15,"log_ni":1e15,"log_nop":1e12,"log_nm":1e12}
BLOCK=re.compile(r"(?ms)^  \[(?P<name>log_ne|log_ni|log_nop|log_nm)\][ \t]*\n(?P<body>.*?)^  \[\][ \t]*(?=\r?$)")
INITIAL=re.compile(r"(?m)^(?P<indent>[ \t]*)initial_condition[ \t]*=[ \t]*[^\r\n#]+(?P<comment>\s*(?:#[^\r\n]*)?)$")

def apply(text: str) -> str:
    matches=list(BLOCK.finditer(text))
    present=[m.group("name") for m in matches]
    if set(present)!=set(SEEDS_M3) or len(present)!=4:
        raise ValueError(f"missing or duplicate charged variable blocks: {present}")
    def sub(m):
        name=m.group("name")
        body=m.group("body")
        if len(INITIAL.findall(body))!=1:
            raise ValueError(f"{name}: require exactly one initial_condition")
        logmol=math.log(SEEDS_M3[name]/N_A)
        new=INITIAL.sub(lambda q: f"{q.group('indent')}initial_condition = {logmol:.17g}",body,count=1)
        return f"  [{name}]\n{new}  []"
    out=BLOCK.sub(sub,text)
    for symbol,value in SEEDS_M3.items():
        if not math.isclose(math.exp(math.log(value/N_A))*N_A,value,rel_tol=2e-15):
            raise ValueError(f"seed conversion failed: {symbol}")
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base-input",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    if a.base_input.resolve()==a.output.resolve():
        raise ValueError("do not overwrite prior reference input")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(apply(a.base_input.read_text()),encoding="utf-8")
    print("OXYGEN_24_CHARGED_SEEDS_APPLIED; n_e=n_O2p=1e15, n_Op=n_Om=1e12 m-3")

if __name__=="__main__":
    main()
