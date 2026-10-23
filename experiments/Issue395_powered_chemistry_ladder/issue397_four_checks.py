#!/usr/bin/env python3
"""Independent read-only verdicts for Issue 403 high-power Maxwell-tolerance cases.

Each case reuses one simulation output; four checks run concurrently.
A PASS means only that the specified diagnostic gates passed, not that the
modified solver tolerance was physically proved equivalent at all powers.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def inspect(result: Path, target_w: int, p3_outcome: str, p4_outcome: str, head_sha: str) -> dict:
    log_path = result / "runtime.log"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""

    csv_path = result / "run" / "plasma.csv"
    rows = []
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    last = rows[-1] if rows else {}
    last_time = float(last.get("time", 0.0))

    def maxwell():
        failures = log.count("DIVERGED_MAX_IT")
        present = "maxwell_t60:" in log
        status = "FAIL" if failures else "PASS" if present and last_time >= 5.8e-8 - 1e-14 else "INCOMPLETE"
        return {"status": status, "child_log_present": present, "max_iteration_failures": failures}

    def threshold_58ns():
        return {
            "status": "PASS" if last_time >= 5.8e-8 - 1e-14 else "FAIL" if rows else "INCOMPLETE",
            "last_accepted_time_us": last_time * 1e6,
            "crossed_historical_58ns": last_time >= 5.8e-8 - 1e-14,
        }

    def pid_power():
        if not rows:
            return {"status": "INCOMPLETE", "reason": "plasma.csv missing"}
        drive = float(last.get("rf_drive_scale_t6", "nan"))
        controlled = float(last.get("P_rf_scaled_W_t6", "nan"))
        absorbed = float(last.get("P_abs_maxwell_t6", "nan"))
        capped = math.isfinite(drive) and drive >= 3.0 - 1e-6
        finite = all(math.isfinite(v) for v in (drive, controlled, absorbed))
        error = abs(controlled - target_w) / target_w if finite else None
        complete = last_time >= 100e-6 - 1e-12
        status = (
            "INCOMPLETE" if not complete else
            "PASS" if finite and not capped and error is not None and error <= 0.05 else "FAIL"
        )
        return {
            "status": status, "target_power_W": target_w,
            "last_scaled_power_W": controlled if math.isfinite(controlled) else None,
            "last_absorbed_power_W": absorbed if math.isfinite(absorbed) else None,
            "last_drive": drive if math.isfinite(drive) else None,
            "original_PID_cap_reached": capped,
            "relative_target_error": error,
            "last_accepted_time_us": last_time * 1e6,
        }

    def physics_integrity():
        summary_path = result / "d1_native" / "d1_native_summary.json"
        if not summary_path.exists():
            return {"status": "INCOMPLETE", "reason": "P4 D1 evidence missing"}
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        correct = (
            summary.get("status") == "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS"
            and summary.get("wafer_faces") == 27
            and summary.get("native_points") == 461
            and abs(summary.get("final_time_us", 0.0) - 100.0) < 0.001
        )
        return {
            "status": "PASS" if correct else "FAIL",
            "d1_status": summary.get("status"),
            "native_points": summary.get("native_points"),
            "wafer_faces": summary.get("wafer_faces"),
            "final_time_us": summary.get("final_time_us"),
            "current_species_sum_rel_rms": summary.get("current_species_sum_rel_rms"),
            "surface_charge_balance_rel_rms": summary.get("surface_charge_balance_rel_rms"),
        }

    checks = {
        "maxwell_convergence": maxwell,
        "historical_58ns": threshold_58ns,
        "rf_power_and_PID": pid_power,
        "physical_integrity_100us": physics_integrity,
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {key: pool.submit(fn) for key, fn in checks.items()}
        verdicts = {key: future.result() for key, future in futures.items()}
    return {
        "experiment": "issue403_700w_verified_baseline_final_power_scan_800_900_1000w",
        "target_power_W": target_w,
        "head_sha": head_sha,
        "p3_outcome": p3_outcome,
        "p4_outcome": p4_outcome,
        "maxwell_abs_tolerance": 1e-11,
        "maxwell_rel_tolerance_unchanged": 1e-10,
        "PID_drive_cap_unchanged": 3.0,
        "checks": verdicts,
        "status": "PASS" if all(v["status"] == "PASS" for v in verdicts.values()) else "NOT_PASS",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--result", type=Path, required=True)
    p.add_argument("--power-w", type=int, required=True, choices=(800, 900, 1000))
    p.add_argument("--p3-outcome", required=True)
    p.add_argument("--p4-outcome", required=True)
    p.add_argument("--head-sha", required=True)
    args = p.parse_args()

    report = inspect(args.result, args.power_w, args.p3_outcome, args.p4_outcome, args.head_sha)
    dest = args.result / "diagnostics"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "four_check_summary.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, allow_nan=False))
    if report["status"] != "PASS":
        raise SystemExit("Four-check acceptance not established; inspect artifact JSON")


if __name__ == "__main__":
    main()
