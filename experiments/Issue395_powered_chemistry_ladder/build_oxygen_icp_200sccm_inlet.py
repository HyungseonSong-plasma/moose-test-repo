#!/usr/bin/env python3
"""Research-only inlet override; must operate on a generated or inherited MOOSE input."""
import argparse
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/"oxygen_icp_operating_200sccm_sticking1.json"
FRACTIONS={"Yin_O2":1,"Yin_O2s":0,"Yin_O2p":0,"Yin_O":0,
           "Yin_Om":0,"Yin_Op":0,"Yin_Os":0}

def replace_unique(text, name, value):
    pat=rf"(?m)^{re.escape(name)}\s*=\s*[^#\r\n]+$"
    hits=re.findall(pat,text)
    if len(hits)!=1:
        raise ValueError(f"require exactly one top-level {name}; found {len(hits)}")
    return re.sub(pat, f"{name} = {value}", text, count=1)

def apply(text):
    if "inlet_mdot_value" not in text or "Vm_std" not in text or "Q_std" not in text:
        raise ValueError("canonical inlet mass-flow conversion not present")
    config=json.loads(CONFIG.read_text())
    text=replace_unique(text,"Q_sccm",str(config["inlet"]["Q_sccm"]))
    for name,value in FRACTIONS.items():
        text=replace_unique(text,name,str(value))
    return text

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base-input",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    if args.base_input.resolve()==args.output.resolve():
        raise ValueError("refusing to replace qualified baseline")
    args.output.write_text(apply(args.base_input.read_text()),encoding="utf-8")
    print("OXYGEN_ICP_200SCCM_INLET_RESEARCH_CONSTRUCTED")
    print("Wall settings must be passed to the research_uniform_sticking option separately.")

if __name__=="__main__":
    main()
