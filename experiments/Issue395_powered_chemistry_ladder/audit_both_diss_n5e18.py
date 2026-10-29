#!/usr/bin/env python3
"""Fail-closed scientific-claim-HOLD runtime auditor for both dissociation channels.

This is separate from the historical source auditor, which audits one DISS channel.
"""
from __future__ import annotations
import argparse
import csv
import importlib.util
import json
import math
from pathlib import Path

CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
ABS=1e-22
REL=2e-5

def near(value, expected, name, tol=REL):
    if not all(map(math.isfinite,(value,expected))):
        raise AssertionError(f"{name}: nonfinite {value} / {expected}")
    if abs(value-expected)>tol*max(abs(value),abs(expected),ABS):
        raise AssertionError(f"{name}: {value} != {expected}")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--result",required=True,type=Path)
    p.add_argument("--detachment",choices=("off","on"),required=True)
    p.add_argument("--p3",required=True)
    p.add_argument("--p4",required=True)
    a=p.parse_args()
    path=CHEM/"analyze_ground_state_power_scan.py"
    spec=importlib.util.spec_from_file_location("pinned_step1_auditor",path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    canonical=mod.audit(a.result,1000,"aa81c1ca1d52e9431b56682b227fe96aa3a305cd",a.p3,a.p4,"ground",True)
    if canonical["status"]!="PASS":
        raise AssertionError("Step1 ground, pure inlet, RF, full time or D1 validation failed: "+json.dumps(canonical["checks"]))
    csv_path=a.result/"run/plasma.csv"
    with csv_path.open(newline="") as f:
        rr=list(csv.DictReader(f))
    if len(rr)!=461 or abs(float(rr[-1]["time"])-1e-4)>1e-12:
        raise AssertionError("100us 461 physical points required")
    mixed=(
      "mixed_R_integral","mixed_energy_sink_integral","mixed_o3p_mass_integral",
      "mixed_o1d_mass_integral","mixed_oxygen_molecular_sink_integral",
      "mixed_heavy_mass_closure_integral")
    det=(
      "edetach_R_integral","edetach_electron_source_integral","edetach_om_source_integral",
      "edetach_o_mass_integral","edetach_neutral_mass_integral",
      "edetach_energy_sink_integral","edetach_mass_closure_integral",
      "edetach_charge_closure_integral")
    if not all(k in rr[0] for k in mixed):
        raise AssertionError("Mixed progress/sinks not present in solver CSV")
    if (a.detachment=="on") != all(k in rr[0] for k in det):
        raise AssertionError("Unexpected EDETACH source presence/absence")
    if a.detachment=="off" and any(k in rr[0] for k in det):
        raise AssertionError("EDETACH OFF contaminated by active detachment diagnostics")
    rate_mixed=[]
    rate_det=[]
    for i,row in enumerate(rr):
        def n(name):
            v=float(row[name])
            if not math.isfinite(v):raise AssertionError(f"{i} {name}: nonfinite")
            return v
        rm=n(mixed[0])
        if rm<-ABS: raise AssertionError(f"negative mixed rate at {i}")
        near(n(mixed[1]),-8.4*rm,"mixed energy")
        near(n(mixed[2]),0.016*rm,"mixed O3P mass")
        near(n(mixed[3]),0.016*rm,"mixed O1D mass")
        near(n(mixed[4]),-0.032*rm,"mixed O2 sink")
        near(n(mixed[5]),0.0,"mixed mass closure")
        rate_mixed.append(rm)
        if a.detachment=="on":
            r=n(det[0])
            if r<-ABS:raise AssertionError(f"negative detach rate at {i}")
            near(n(det[1]),r,"detach electron source")
            near(n(det[2]),-r,"detach negative ion source")
            near(n(det[3]),0.016*r,"detach neutral O source")
            near(n(det[4]),0.016*r,"detach neutral gas source")
            near(n(det[5]),-1.4611*r,"detach 1.4611eV energy sink")
            near(n(det[6]),0.0,"detach heavy mass closure")
            near(n(det[7]),0.0,"detach charge closure")
            rate_det.append(r)
    # First study with both concurrently enabled; independently auditable progress owners.
    if not all(k in rr[0] for k in ("diss_R_integral","diss_energy_source_integral","diss_O_mass_source_integral")):
        raise AssertionError("Ground dissociation progress missing from combined physics")
    report={
        "status":"PASS","science_acceptance":"HOLD",
        "target_power_W":1000,"initial_O3P_number_density_m3":5e18,
        "ground_dissociation":"ON","mixed_dissociation":"ON",
        "EDETACH_OM":a.detachment.upper(),"detachment_energy_loss_eV_event":1.4611 if a.detachment=="on" else None,
        "source_sha":"aa81c1ca1d52e9431b56682b227fe96aa3a305cd",
        "points":len(rr),"last_time_us":float(rr[-1]["time"])*1e6,
        "last_R_ground_mol_s":float(rr[-1]["diss_R_integral"]),
        "last_R_mixed_mol_s":rate_mixed[-1],
        "last_R_detach_mol_s":rate_det[-1] if rate_det else None,
        "canonical_step1_checks":canonical["checks"],
        "reaction_ownership_and_chemistry_closure":"PASS"
    }
    out=a.result/"diagnostics"/"both_diss_n5e18_validation.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps(report,indent=2,allow_nan=False))
    print("ISSUE395_DUAL_DISS_N5E18_P5_PASS")

if __name__=="__main__":
    main()
