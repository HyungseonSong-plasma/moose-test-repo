#!/usr/bin/env python3
"""Exclusively assess H02 or H03 against the unchanged original B-case."""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path

M_O=0.016
STOICH={"H02":2,"H03":3}
ABS=1e-22
REL=2e-5

def near(x,y,name):
    if not math.isfinite(x) or not math.isfinite(y): raise AssertionError(f"{name}: nonfinite")
    if abs(x-y)>REL*max(abs(x),abs(y),ABS):raise AssertionError(f"{name}: {x} != {y}")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--result",required=True,type=Path)
    p.add_argument("--arm",required=True,choices=STOICH)
    a=p.parse_args()
    rows=list(csv.DictReader((a.result/"run/plasma.csv").open(newline="")))
    if len(rows)!=461 or not math.isclose(float(rows[-1]["time"]),1e-4,rel_tol=0,abs_tol=1e-12):
        raise AssertionError("Full 100us 461-point history required")
    names=[
      "R_integral","om_sink_integral","positive_sink_integral","o_mass_integral",
      "neutral_mass_integral","mass_closure_integral","charge_closure_integral"
    ]
    cols=["{}_{}".format(a.arm.lower(),name) for name in names]
    others=("H03" if a.arm=="H02" else "H02").lower()+"_R_integral"
    for col in cols:
        if col not in rows[0]:raise AssertionError("Missing reaction field "+col)
    if others in rows[0]:raise AssertionError("Nonselected heavy reaction was active")
    if "edetach_R_integral" not in rows[0]:raise AssertionError("B-case detachment missing")
    for t,row in enumerate(rows):
        def n(k):
            v=float(row[k])
            if not math.isfinite(v):raise AssertionError("nonfinite at "+str(t)+": "+k)
            return v
        r=n(cols[0])
        if r < -ABS:raise AssertionError("negative heavy rate at "+str(t))
        near(n(cols[1]),-r,"negative-ion molar sink")
        near(n(cols[2]),-r,"positive-ion molar sink")
        near(n(cols[3]),STOICH[a.arm]*M_O*r,"O mass production")
        near(n(cols[4]),STOICH[a.arm]*M_O*r,"neutral-gas mass production")
        near(n(cols[5]),0.0,"heavy mass closure")
        near(n(cols[6]),0.0,"electric charge closure")
    out={
      "status":"PASS","science_status":"HOLD",
      "case":"B+"+a.arm,"heavy_reaction_only":a.arm,
      "target_power_W":1000,"initial_O3P_number_density_m3":5e18,
      "ground_state_dissociation":"ON","mixed_state_dissociation":"ON",
      "EDETACH_OM":"ON","detachment_energy_loss_eV":1.4611,
      "source_base_sha":"aa81c1ca1d52e9431b56682b227fe96aa3a305cd",
      "time_points":len(rows),"last_time_us":float(rows[-1]["time"])*1e6,
      "last_R_heavy_mol_s":float(rows[-1][cols[0]]),
      "last_R_detach_mol_s":float(rows[-1]["edetach_R_integral"]),
      "owner_exclusivity_and_mass_charge_balance":"PASS",
      "heavy_reaction_energy_note":"No electron-energy term; neutral thermal heating/radiation not resolved",
    }
    file=a.result/"diagnostics"/("B_plus_"+a.arm+"_chemistry_audit.json")
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    print(json.dumps(out,indent=2,allow_nan=False))
    print("ISSUE395_B_PLUS_"+a.arm+"_P5_PASS")

if __name__=="__main__":main()
