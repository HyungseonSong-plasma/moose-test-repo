#!/usr/bin/env python3
"""Analyze 100 W RF + EI02 elastic + O2 dissociation + EI16 ionization to 15 us."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import analyze_rf_elastic_diss_multiapp_100w_15us as base

FINAL_TIME = 1.5e-5
CLOSURE_TOL = 1.0e-18


def paths(argv: list[str]) -> tuple[Path | None, Path | None]:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--csv", type=Path)
    ns, _ = ap.parse_known_args(argv)
    return ns.output, ns.csv


def main() -> int:
    out, csv_path = paths(sys.argv[1:])
    rc = base.main()
    if out is None or csv_path is None or not out.exists() or not csv_path.exists():
        return rc

    report = json.loads(out.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    last = rows[-1]
    failures = list(report.get("failures", []))

    rmax = float(last.get("ei16_R_ion_O2_max", "nan"))
    rint = float(last.get("ei16_R_ion_O2_integral", "nan"))
    esrc = float(last.get("ei16_energy_source_integral", "nan"))
    mclosure = float(last.get("ei16_heavy_mass_closure_integral", "nan"))
    qclosure = float(last.get("ei16_charge_molar_closure_integral", "nan"))

    if not (rmax > 0.0 and rint > 0.0):
        failures.append("EI16 ionization progress absent")
    if not esrc < 0.0:
        failures.append("EI16 electron-energy contribution not sink")
    if abs(mclosure) > CLOSURE_TOL:
        failures.append("EI16 heavy-mass closure")
    if abs(qclosure) > CLOSURE_TOL:
        failures.append("EI16 charge closure")

    report["gate"] = (
        "continuous plasma-Maxwell MultiApp + EI02 elastic + source-backed O2 dissociation "
        "+ EI16 O2 ionization + 100 W absorbed-RF PID, 0-15 us"
    )
    report["classification"] = (
        "ISSUE395_RF_ELASTIC_DISS_EI16_MULTIAPP_15US_PASS"
        if not failures
        else "ISSUE395_RF_ELASTIC_DISS_EI16_MULTIAPP_15US_FAIL"
    )
    report["status"] = "PASS" if not failures else "FAIL"
    report["failures"] = failures
    report["final"]["requested_final_time_s"] = FINAL_TIME
    report["ionization"] = {
        "channel": "EI16 e + O2 -> 2e + O2+",
        "energy_loss_eV_per_event": 12.06,
        "R_ion_O2_max_final_mol_m3_s": rmax,
        "R_ion_O2_integral_final_mol_s": rint,
        "energy_source_final_eV_mol_s": esrc,
        "heavy_mass_closure_final_kg_s": mclosure,
        "charge_molar_closure_final_mol_s": qclosure,
    }
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE395_RF_ELASTIC_DISS_EI16_MULTIAPP_100W_15US_ANALYSIS")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
