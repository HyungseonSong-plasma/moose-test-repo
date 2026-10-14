#!/usr/bin/env python3
"""Analyze Issue #395 single-execution RF+EI02 MultiApp evidence."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
T6 = ROOT / "experiments" / "Issue376_maxwell_plasma_rf_transfer"
sys.path.insert(0, str(T6))
import run_t6_representative_icp as base  # noqa: E402

TARGET_W = 1000.0
POWER_GUARD = 2.0e-2
TABLE_LO = 1.40991
TABLE_HI = 22.1378
FINAL_TIME = 1.10e-7


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def f(row, key):
    return float(row[key])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exodus", type=Path, required=True)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()

    st = base.exodus(a.exodus)
    times = np.asarray(st["times"], dtype=float)
    nodes = np.unique(st["blocks"]["plasma"].reshape(-1))
    ln = st["nodal"]["log_ne"][-1][nodes]
    le = st["nodal"]["log_energy"][-1][nodes]
    mean_en = np.exp(le - ln)
    rows = read_rows(a.csv)
    if not rows:
        raise RuntimeError("empty parent CSV")

    valid = [r for r in rows if float(r.get("time", r.get("Time", "0"))) > 0]
    if not valid:
        valid = rows

    pmax = [f(r, "P_abs_maxwell_t6") for r in valid]
    ptgt = [f(r, "P_rf_scaled_W_t6") for r in valid]
    drive = [f(r, "rf_drive_scale_t6") for r in valid]
    max_err = max(abs(p - TARGET_W) / TARGET_W for p in pmax)
    tgt_err = max(abs(p - TARGET_W) / TARGET_W for p in ptgt)

    direction_violations = 0
    for i in range(1, len(valid)):
        prev_err = pmax[i - 1] - TARGET_W
        ds = drive[i] - drive[i - 1]
        if prev_err > 1e-6 and ds > 1e-10:
            direction_violations += 1
        if prev_err < -1e-6 and ds < -1e-10:
            direction_violations += 1

    last = valid[-1]
    failures = []
    if abs(float(times[-1]) - FINAL_TIME) > 5e-15:
        failures.append("did not reach 110 ns")
    if max_err > POWER_GUARD:
        failures.append("Maxwell absorbed-power ±2% guardrail")
    if tgt_err > POWER_GUARD:
        failures.append("target-grid RF ±2% guardrail")
    if direction_violations:
        failures.append("PID feedback direction")
    emin = float(np.min(mean_en))
    emax = float(np.max(mean_en))
    if not (TABLE_LO <= emin <= emax <= TABLE_HI):
        failures.append("RF transport mean-energy range")
    if float(last.get("elastic_R_max", "0")) <= 0:
        failures.append("elastic progress absent")
    if float(last.get("elastic_energy_source_integral", "0")) >= 0:
        failures.append("elastic term not sink")

    report = {
        "issue": 395,
        "gate": "single-execution plasma-Maxwell MultiApp + EI02 elastic + lagged 1000 W PID",
        "status": "PASS" if not failures else "FAIL",
        "classification": "ISSUE395_RF_ELASTIC_MULTIAPP_110NS_PASS" if not failures else "ISSUE395_RF_ELASTIC_MULTIAPP_110NS_FAIL",
        "architecture": {
            "parent": "continuous transient plasma",
            "child": "FullSolveMultiApp steady Maxwell at TIMESTEP_BEGIN",
            "external_probe": False,
            "rollback": False,
            "recover_between_steps": False,
            "external_solution_file_coupling": False,
            "power_feedback": "P_abs_maxwell_t6 -> PIDTransientControl -> rf_drive_scale_t6 -> child coil amplitude next timestep",
        },
        "power": {
            "target_W": TARGET_W,
            "max_Maxwell_relative_error": max_err,
            "max_target_grid_relative_error": tgt_err,
            "final_Maxwell_W": pmax[-1],
            "final_target_grid_W": ptgt[-1],
            "final_drive_scale": drive[-1],
            "feedback_direction_violations": direction_violations,
        },
        "final": {
            "time_s": float(times[-1]),
            "mean_energy_min_eV": emin,
            "mean_energy_max_eV": emax,
            "elastic_R_max": float(last.get("elastic_R_max", "nan")),
            "elastic_energy_source_eV_mol_s": float(last.get("elastic_energy_source_integral", "nan")),
        },
        "failures": failures,
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
