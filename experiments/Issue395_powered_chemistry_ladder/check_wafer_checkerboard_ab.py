#!/usr/bin/env python3
"""A/B probe of wafer lower-D sigma assembly on the accepted 200W EI17 input.

A: force uniform +0.25 A/m^2 wafer current, keep full plasma/Poisson/sheath coupling.
   Run to 1 us, expect sigma_i(t)=0.25*t for every wafer surface element.
B: preserve physical current exactly, add per-face higher-D FV current diagnostic.
   Run to 60 us and test sigma implicit-Euler rate against independent current probe.
The only changed science in B is the observation and early termination at 60 us.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

CURRENT_BLOCK = re.compile(r"(?ms)^  \[wafer_surface_current\]\n.*?^  \[\]\n")
EXEC_TIME = re.compile(r"(?m)^  end_time\s*=\s*\S+\s*$")
TIME_SEQUENCE = re.compile(r"(?m)^    time_sequence\s*=\s*'([^']+)'\s*$")
CURRENT_J_A_M2=0.25
MODE_FINAL_NS={"A":1000, "B":60000}


def transform(src: str, mode: str) -> tuple[str,int]:
    if mode not in MODE_FINAL_NS:raise ValueError(mode)
    if src.count("[wafer_surface_current]")!=1:raise ValueError("exact wafer current material required")
    if src.count("[Executioner]")!=1:raise ValueError("one executioner required")
    if "[AuxVariables]" in src or "[AuxKernels]" in src:
        raise ValueError("diagnostic input assumes baseline has no AuxVariables/AuxKernels")
    old=CURRENT_BLOCK.search(src)
    if not old:raise ValueError("wafer_surface_current material block not found")
    if "wafer_net_surface_current_density" not in old.group(0):raise ValueError("unexpected wafer current property")
    if mode=="A":
        repl="""  [wafer_surface_current]
    type = ADParsedFunctorMaterial
    property_name = wafer_net_surface_current_density
    expression = '0.25'
    block = plasma
  []
"""
        src=src[:old.start()]+repl+src[old.end():]
    else:
        if "expression = '1.602176634e-19*(gi+gop-gm-ge)'" not in old.group(0):
            raise ValueError("physical current owner mutated")

    aux="""[AuxVariables]
  [wafer_net_current_probe]
    family = MONOMIAL
    order = CONSTANT
    block = wafer_surface
  []
[]
[AuxKernels]
  [wafer_net_current_probe_kernel]
    type = PhysicsLowerDSurfaceCurrentProbeAux
    variable = wafer_net_current_probe
    surface_current_density = wafer_net_surface_current_density
    block = wafer_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""
    src=src.replace("[Executioner]\n",aux+"[Executioner]\n",1)

    target_ns=MODE_FINAL_NS[mode]
    src,n_end=EXEC_TIME.subn(f"  end_time = {target_ns * 1e-9:.17g}",src,count=1)
    if n_end!=1:raise ValueError("end_time count mismatch")
    ts=TIME_SEQUENCE.search(src)
    if not ts:raise ValueError("base time_sequence missing")
    seq=[float(v) for v in ts.group(1).split()]
    retained=[t for t in seq if t<=target_ns*1e-9+1e-15]
    if not retained or abs(retained[-1]-target_ns*1e-9)>1e-14 or retained[0]!=0:
        raise ValueError("truncated sequence not aligned")
    expected_steps=190 if mode=="A" else 420
    if len(retained)!=expected_steps+1:
        raise ValueError(f"unexpected {len(retained)-1} time steps; expected {expected_steps}")
    repl_seq="    time_sequence = '"+ " ".join(f"{v:.17g}" for v in retained) +"'"
    src=src[:ts.start()]+repl_seq+src[ts.end():]
    if "time_sequence = '"+ " ".join(f"{v:.17g}" for v in retained) +"'" not in src:
        raise ValueError("time sequence serialization failure")
    if src.count("type = PhysicsLowerDSurfaceCurrentProbeAux")!=1:
        raise ValueError("probe not installed")
    return src,expected_steps


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("input",type=Path)
    ap.add_argument("--mode",required=True,choices=sorted(MODE_FINAL_NS))
    args=ap.parse_args()
    transformed,steps=transform(args.input.read_text(),args.mode)
    args.input.write_text(transformed)
    print(f"ISSUE395_WAFER_CHECKERBOARD_TEST_{args.mode}_INPUT_PASS")
    print(f"steps={steps} end_time_ns={MODE_FINAL_NS[args.mode]}")
    print("sigma initial condition unchanged, mesh and sigma FE family unchanged")
    print("wafer current = uniform +0.25 A/m2" if args.mode=="A" else "wafer current = original gi+gop-gm-ge")
    print("wafer_current_probe = original face-functor sampled per lower-D surface element")


if __name__=="__main__":
    main()
