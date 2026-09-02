#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

def rel(a, b):
    return abs(a-b)/max(abs(a),abs(b),1e-300)

def load(csv_path):
    with Path(csv_path).open(newline="") as f:
        rows=list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"no rows in {csv_path}")
    return min(rows,key=lambda r: abs(float(r["time"]))), max(rows,key=lambda r: float(r["time"]))

def correction_on(csv_path):
    r0,r1=load(csv_path)
    sum_err=max(abs(float(r1["sum_w_min"])-1.0),abs(float(r1["sum_w_max"])-1.0))
    ion_mass_err=rel(float(r1["ion_mass"]),float(r0["ion_mass"]))
    neutral_mass_err=rel(float(r1["neutral_mass"]),float(r0["neutral_mass"]))
    positive=float(r1["ion_min"])>=-1e-12 and float(r1["neutral_min"])>=-1e-12
    ok=sum_err<1e-9 and ion_mass_err<1e-10 and neutral_mass_err<1e-10 and positive
    print(f"sum_w_err={sum_err:.6e}")
    print(f"ion_mass_err={ion_mass_err:.6e}")
    print(f"neutral_mass_err={neutral_mass_err:.6e}")
    print("CORRECTION_ON:","PASS" if ok else "FAIL")
    return ok

def poisson_analytic(csv_path):
    _,r=load(csv_path)
    e=1.602176634e-19; NA=6.02214076e23; eps0=8.8541878128e-12
    rho=1e-9; w=1e-6; M=0.032003320316217242
    S=e*rho*w*NA/(M*eps0)
    w_err=rel(float(r["w_avg"]),w)
    phi_max_err=rel(float(r["phi_max"]),S/8.0)
    phi_avg_err=rel(float(r["phi_avg"]),S/12.0)
    ok=w_err<1e-8 and phi_max_err<2e-2 and phi_avg_err<2e-2
    print(f"w_err={w_err:.6e}")
    print(f"phi_max_err={phi_max_err:.6e}")
    print(f"phi_avg_err={phi_avg_err:.6e}")
    print("POISSON_ANALYTIC:","PASS" if ok else "FAIL")
    return ok

def self_consistent(csv_path):
    r0,r1=load(csv_path)
    m0=float(r0["ion_mass"]); m1=float(r1["ion_mass"])
    n0=float(r0["neutral_mass"]); n1=float(r1["neutral_mass"])
    ion_mass_err=rel(m1,m0); neutral_mass_err=rel(n1,n0)
    sum_err=max(abs(float(r1["sum_w_min"])-1.0),abs(float(r1["sum_w_max"])-1.0))
    c0=float(r0["ion_first_moment_x"])/m0
    c1=float(r1["ion_first_moment_x"])/m1
    positive=float(r1["ion_min"])>=-1e-14 and float(r1["neutral_min"])>=-1e-14
    ok=ion_mass_err<1e-8 and neutral_mass_err<1e-8 and sum_err<1e-8 and positive and float(r1["phi_max"])>0 and c1<c0
    print(f"ion_mass_err={ion_mass_err:.6e}")
    print(f"neutral_mass_err={neutral_mass_err:.6e}")
    print(f"sum_w_err={sum_err:.6e}")
    print(f"centroid_shift={c1-c0:.6e}")
    print(f"phi_max={float(r1['phi_max']):.6e}")
    print("SELF_CONSISTENT_2D:","PASS" if ok else "FAIL")
    return ok

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("usage: check_reactor_o2plus.py CSV MODE")
    csv_path,mode=sys.argv[1],sys.argv[2]
    checks={"correction_on":correction_on,"poisson_analytic":poisson_analytic,"self_consistent":self_consistent}
    if mode not in checks:
        raise SystemExit(f"unknown mode: {mode}")
    raise SystemExit(0 if checks[mode](csv_path) else 1)
