#!/usr/bin/env python3
"""Analyze Issue #395 continuous 100 W RF + EI02 elastic + O2 dissociation."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import analyze_rf_elastic_multiapp as base

TARGET_W = 100.0
FINAL_TIME = 1.0e-7
DISS_ENERGY_LOSS_EV = 12.62
HEAVY_MASS_CLOSURE_TOL = 1.0e-18


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def output_and_csv(argv: list[str]) -> tuple[Path | None, Path | None]:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--csv", type=Path)
    ns, _ = ap.parse_known_args(argv)
    return ns.output, ns.csv


def main() -> int:
    out, csv_path = output_and_csv(sys.argv[1:])
    base.TARGET_W = TARGET_W
    base.FINAL_TIME = FINAL_TIME
    rc = base.main()

    if out is None or csv_path is None or not out.exists():
        return rc

    report = json.loads(out.read_text(encoding="utf-8"))
    rows = read_rows(csv_path)
    last = rows[-1]
    failures = list(report.get("failures", []))

    diss_r_max = float(last.get("diss_R_max", "nan"))
    diss_r_integral = float(last.get("diss_R_integral", "nan"))
    diss_energy = float(last.get("diss_energy_source_integral", "nan"))
    diss_o_mass = float(last.get("diss_O_mass_source_integral", "nan"))
    heavy_closure = float(last.get("diss_heavy_mass_closure_integral", "nan"))

    if not (diss_r_max > 0.0 and diss_r_integral > 0.0):
        failures.append("dissociation progress absent")
    if not diss_energy < 0.0:
        failures.append("dissociation electron-energy term not sink")
    if abs(heavy_closure) > HEAVY_MASS_CLOSURE_TOL:
        failures.append("dissociation heavy-mass closure")

    report["gate"] = (
        "single-execution plasma-Maxwell MultiApp + EI02 elastic + source-backed O2 dissociation "
        "+ 100 W absorbed-RF PID, 0-100 ns"
    )
    report["classification"] = (
        "ISSUE395_RF_ELASTIC_DISS_MULTIAPP_100NS_PASS"
        if not failures
        else "ISSUE395_RF_ELASTIC_DISS_MULTIAPP_100NS_FAIL"
    )
    report["status"] = "PASS" if not failures else "FAIL"
    report["failures"] = failures
    report["power"]["target_W"] = TARGET_W
    report["final"]["requested_final_time_s"] = FINAL_TIME
    report["chemistry"] = {
        "active_channels": ["EI02_O2_ELASTIC", "EI_DISS_O2_TO_2O_SOURCE_BACKED"],
        "dissociation_energy_loss_eV_per_event": DISS_ENERGY_LOSS_EV,
        "dissociation_rate_model": "1.41e-15*Te^0.22*exp(-12.62/Te), Te=(2/3)*mean_en_solved",
        "historical_O2_dissociation_csv_used": False,
        "diss_R_max_final_mol_m3_s": diss_r_max,
        "diss_R_integral_final_mol_s": diss_r_integral,
        "diss_energy_source_final_eV_mol_s": diss_energy,
        "diss_O_mass_source_final_kg_s": diss_o_mass,
        "diss_heavy_mass_closure_final_kg_s": heavy_closure,
    }
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE395_RF_ELASTIC_DISS_MULTIAPP_100W_ANALYSIS")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
