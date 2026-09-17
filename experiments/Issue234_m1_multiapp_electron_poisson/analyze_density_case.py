#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

EPS0 = 8.8541878128e-12
E_CHARGE = 1.602176634e-19
MU_E = 9755.114369721427
DT_E = 1.0e-10
TARGET_END = 1.0e-9

ROOT = Path(__file__).resolve().parent

def rows(path: Path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def fval(row, key):
    try:
        return float(row[key])
    except Exception:
        return math.nan

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ne", type=float, required=True)
    ap.add_argument("--runtime-rc", type=int, required=True)
    args = ap.parse_args()

    ne0 = args.ne
    tau = EPS0 / (E_CHARGE * MU_E * ne0)
    electron_csv = ROOT / "heavy_parent_scan_out_electron_fast0.csv"
    parent_csv = ROOT / "heavy_parent_scan_out.csv"
    runtime_log = ROOT / "runtime_density_scan.log"

    erows = rows(electron_csv)
    prows = rows(parent_csv)
    last_e = erows[-1] if erows else {}
    last_p = prows[-1] if prows else {}

    profile_files = sorted(ROOT.glob("heavy_parent_scan_out_electron_fast0_electron_profile_*.csv"))
    profiles = []
    for path in profile_files:
        rr = rows(path)
        if not rr:
            continue
        pts=[]
        for r in rr:
            try:
                pts.append((float(r["x"]), float(r["electron_density_out"]), float(r["potential_from_poisson"])))
            except Exception:
                pass
        if not pts:
            continue
        pts.sort()
        peak=max(pts,key=lambda x:x[1])
        profiles.append({
            "file": path.name,
            "peak_x_m": peak[0],
            "peak_ne_m3": peak[1],
            "peak_phi_V": peak[2],
            "left_ne_m3": pts[0][1],
            "right_ne_m3": pts[-1][1],
            "right_to_left_ratio": pts[-1][1] / max(pts[0][1], 1e-300),
        })

    logtxt = runtime_log.read_text(errors="replace") if runtime_log.exists() else ""
    failure_tokens = []
    for token in (
        "DIVERGED_FUNCTION_NANORINF",
        "DIVERGED_BREAKDOWN",
        "DIVERGED_LINE_SEARCH",
        "DIVERGED_MAX_IT",
        "timestep already at or below dtmin",
    ):
        if token in logtxt:
            failure_tokens.append(token)

    times=[fval(r,"time") for r in erows if "time" in r]
    times=[x for x in times if math.isfinite(x)]
    last_e_time=max(times) if times else math.nan
    completed = args.runtime_rc == 0 and math.isfinite(last_e_time) and last_e_time >= TARGET_END*(1-1e-9)

    summary={
        "ne0_m3": ne0,
        "tau_dielectric_s": tau,
        "electron_dt_s": DT_E,
        "dt_over_tau": DT_E/tau,
        "runtime_rc": args.runtime_rc,
        "completed_full_1ns": completed,
        "last_converged_electron_time_s": last_e_time,
        "electron_rows": len(erows),
        "parent_rows": len(prows),
        "last_n_e_min_m3": fval(last_e,"n_e_min") if last_e else math.nan,
        "last_n_e_max_m3": fval(last_e,"n_e_max") if last_e else math.nan,
        "last_phi_min_V": fval(last_e,"phi_min") if last_e else math.nan,
        "last_phi_max_V": fval(last_e,"phi_max") if last_e else math.nan,
        "failure_tokens": failure_tokens,
        "profile_count": len(profiles),
        "profiles": profiles,
        "science_claim": False,
        "claim_scope": "density-scaling discriminator for electron-Poisson lagged feedback stability",
    }
    out=ROOT/"density_scan_summary.json"
    out.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print(json.dumps(summary,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
