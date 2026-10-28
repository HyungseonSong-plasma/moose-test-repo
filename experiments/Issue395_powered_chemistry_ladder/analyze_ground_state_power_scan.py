#!/usr/bin/env python3
"""Bounded read-only analysis of the corrected O2 ground-state 3-power run.

This audit reports chemistry-specific progress/energy/mass identities separately
from solver convergence, delivered RF power and wafer D1 integrity. It never
promotes a historical result or incomplete run to new scientific acceptance.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

POWER_CASES = (200, 400, 600, 1000)
RATE_TOL = 2e-5
SOURCE_TOL = 2e-5


def audit(result: Path, power_w: int, source_sha: str, p3: str, p4: str, diss_channel: str = "ground") -> dict:
    csv_file = result / "run" / "plasma.csv"
    rows = []
    if csv_file.is_file():
        with csv_file.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    last = rows[-1] if rows else {}
    if diss_channel == "mixed":
        required = (
            "mixed_R_integral", "mixed_energy_sink_integral",
            "mixed_o3p_mass_integral", "mixed_o1d_mass_integral",
            "mixed_oxygen_molecular_sink_integral", "mixed_heavy_mass_closure_integral",
        )
        energy_per_event, o3p_mass_per_event = 8.4, 0.016
    else:
        required = (
            "diss_R_integral", "diss_energy_source_integral",
            "diss_O_mass_source_integral", "diss_heavy_mass_closure_integral",
        )
        energy_per_event, o3p_mass_per_event = 6.0, 0.032
    chemistry: dict[str, object] = {"status": "INCOMPLETE", "required_columns": list(required)}
    missing = [field for field in required if field not in last]
    if not missing:
        try:
            observations = [float(last[name]) for name in required]
            finite = all(map(math.isfinite, observations))
            rate, energy, oxygen = observations[:3]
            closure = observations[-1]
            energy_tol = SOURCE_TOL * max(abs(energy), abs(energy_per_event * rate), 1e-20)
            oxygen_tol = SOURCE_TOL * max(abs(oxygen), abs(o3p_mass_per_event * rate), 1e-20)
            close_tol = SOURCE_TOL * max(abs(oxygen), 1e-20)
            valid = (finite and rate >= 0 and
                     abs(energy + energy_per_event * rate) <= energy_tol and
                     abs(oxygen - o3p_mass_per_event * rate) <= oxygen_tol and
                     abs(closure) <= close_tol)
            chemistry = {
                "status": "PASS" if valid else "FAIL",
                "reaction_progress_mol_s_integral": rate,
                "electron_energy_sink_eV_mol_s_integral": energy,
                "atomic_O3P_mass_source_kg_s_integral": oxygen,
                "heavy_mass_closure_integral": closure,
                "energy_ratio_expected": -energy_per_event,
                "O3P_mass_ratio_expected": o3p_mass_per_event,
                "all_finite": finite,
            }
            if diss_channel == "mixed":
                excited, o2_sink = observations[3:5]
                extra_ok = (
                    abs(excited - 0.016 * rate) <= SOURCE_TOL * max(abs(excited), 1e-20)
                    and abs(o2_sink + 0.032 * rate) <= SOURCE_TOL * max(abs(o2_sink), 1e-20)
                    and abs(oxygen + excited + o2_sink) <= SOURCE_TOL * max(
                        abs(oxygen), abs(excited), abs(o2_sink), 1e-20
                    )
                )
                if not extra_ok:
                    chemistry["status"] = "FAIL"
                chemistry["atomic_O1D_mass_source_kg_s_integral"] = excited
                chemistry["implicit_O2_mass_sink_kg_s_integral"] = o2_sink
                chemistry["O1D_mass_ratio_expected"] = 0.016
                chemistry["O2_mass_ratio_expected"] = -0.032
        except (ValueError, TypeError):
            chemistry = {"status": "FAIL", "reason": "nonnumeric reaction observations"}
    else:
        chemistry["missing_columns"] = missing

    final_time_s = float(last.get("time", "nan")) if last else float("nan")
    complete = math.isfinite(final_time_s) and final_time_s >= 100e-6 - 1e-12
    d1_file = result / "d1_native" / "d1_native_summary.json"
    d1 = json.loads(d1_file.read_text(encoding="utf-8")) if d1_file.is_file() else None
    d1_ok = (
        isinstance(d1, dict)
        and d1.get("status") == "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS"
        and d1.get("wafer_faces") == 27
        and d1.get("native_points") == 461
        and abs(float(d1.get("final_time_us", 0)) - 100.0) < 0.001
    )
    def number(name: str) -> float | None:
        try:
            v = float(last.get(name, "nan"))
            return v if math.isfinite(v) else None
        except (ValueError, TypeError):
            return None
    drive = number("rf_drive_scale_t6")
    scaled_w = number("P_rf_scaled_W_t6")
    absorbed_w = number("P_abs_maxwell_t6")
    capped = drive is not None and drive >= 3.0 - 1e-6
    relative_power_error = abs(scaled_w - power_w) / power_w if scaled_w is not None else None
    pid_status = (
        "INCOMPLETE" if not complete else
        "PASS" if (drive is not None and scaled_w is not None and absorbed_w is not None
                   and not capped and relative_power_error is not None and relative_power_error <= 0.05)
        else "FAIL"
    )
    runtime_log = (result / "runtime.log")
    log = runtime_log.read_text(encoding="utf-8", errors="replace") if runtime_log.is_file() else ""
    maxwell_failed = "DIVERGED_MAX_IT" in log
    state = {
        "target_power_W": power_w,
        "source_sha": source_sha,
        "model": ("O2_ground_state_O3P_plus_O3P" if diss_channel == "ground"
                  else "O2_mixed_O3P_plus_O1D"),
        "reaction_fit": ("1.41e-15*Te^-0.22*exp(-2.98/Te)" if diss_channel == "ground"
                         else "3.49e-14*exp(-5.92/Te)"),
        "effective_electron_energy_loss_eV": energy_per_event,
        "science_status": "HOLD_CROSS_SECTION_EEPF_QUENCHING" if diss_channel == "mixed" else "HOLD_SOURCE_PARITY",
        "p3_outcome": p3,
        "p4_outcome": p4,
        "last_accepted_time_us": final_time_s * 1e6 if math.isfinite(final_time_s) else None,
        "observed_time_points": len(rows),
        "checks": {
            "dissociation_sources": chemistry,
            "rf_power_delivery": {
                "status": pid_status, "requested_W": power_w,
                "scaled_W": scaled_w, "absorbed_W": absorbed_w,
                "PID_drive": drive, "original_PID_cap_reached": capped,
                "relative_target_error": relative_power_error,
            },
            "solver_completion": {
                "status": ("FAIL" if maxwell_failed else
                           "PASS" if complete and p3 == "success" else "INCOMPLETE"),
                "maxwell_DIVERGED_MAX_IT": maxwell_failed,
                "reached_100_us": complete,
            },
            "wafer_D1_integrity": {
                "status": "PASS" if d1_ok else "FAIL" if d1 is not None else "INCOMPLETE",
                "wafer_faces": d1.get("wafer_faces") if d1 else None,
                "native_points": d1.get("native_points") if d1 else None,
            },
        },
    }
    state["status"] = ("PASS" if all(c["status"] == "PASS" for c in state["checks"].values())
                       else "NOT_PASS")
    return state


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--result", type=Path, required=True)
    p.add_argument("--power-w", type=int, choices=POWER_CASES, required=True)
    p.add_argument("--source-sha", required=True)
    p.add_argument("--p3-outcome", required=True)
    p.add_argument("--p4-outcome", required=True)
    p.add_argument("--channel", choices=("ground", "mixed"), default="ground")
    args = p.parse_args()
    report = audit(args.result, args.power_w, args.source_sha, args.p3_outcome, args.p4_outcome, args.channel)
    dest = args.result / "diagnostics" / ("mixed_o3p_o1d_two_power.json" if args.channel == "mixed" else "ground_state_three_power.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
