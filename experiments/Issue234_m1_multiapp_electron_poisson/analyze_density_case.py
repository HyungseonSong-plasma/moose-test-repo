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


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1.0e-10, abs_tol=max(1.0e-30, abs(b) * 1.0e-12))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ne", type=float, required=True)
    ap.add_argument("--dt-e", type=float, required=True)
    ap.add_argument("--expected-steps", type=int, default=20)
    ap.add_argument("--runtime-rc", type=int, required=True)
    args = ap.parse_args()

    ne0 = args.ne
    requested_dt = args.dt_e
    expected_steps = args.expected_steps
    expected_end = requested_dt * expected_steps
    tau = EPS0 / (E_CHARGE * MU_E * ne0)

    electron_csv = ROOT / "heavy_parent_scan_out_electron_fast0.csv"
    parent_csv = ROOT / "heavy_parent_scan_out.csv"
    runtime_log = ROOT / "runtime_density_scan.log"

    erows = rows(electron_csv)
    prows = rows(parent_csv)
    last_e = erows[-1] if erows else {}

    profile_files = sorted(ROOT.glob("heavy_parent_scan_out_electron_fast0_electron_profile_*.csv"))
    profiles = []
    for path in profile_files:
        rr = rows(path)
        if not rr:
            continue
        pts = []
        for r in rr:
            try:
                pts.append(
                    (
                        float(r["x"]),
                        float(r["electron_density_out"]),
                        float(r["potential_from_poisson"]),
                    )
                )
            except Exception:
                pass
        if not pts:
            continue
        pts.sort()
        peak = max(pts, key=lambda x: x[1])
        match = re.search(r"_([0-9]+)\\.csv$", path.name)
        output_step = int(match.group(1)) if match else None
        profiles.append(
            {
                "file": path.name,
                "output_step": output_step,
                "peak_x_m": peak[0],
                "peak_ne_m3": peak[1],
                "peak_phi_V": peak[2],
                "min_ne_m3": min(p[1] for p in pts),
                "max_ne_m3": max(p[1] for p in pts),
                "min_phi_V": min(p[2] for p in pts),
                "max_phi_V": max(p[2] for p in pts),
                "left_ne_m3": pts[0][1],
                "right_ne_m3": pts[-1][1],
                "right_to_left_ratio": pts[-1][1] / max(pts[0][1], 1e-300),
            }
        )

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

    runtime_pattern = re.compile(
        r"electron_fast0:.*?Time Step\s+(\d+),\s*time\s*=\s*"
        r"([0-9eE+\-.]+),\s*dt\s*=\s*([0-9eE+\-.]+)"
    )
    runtime_steps = []
    for match in runtime_pattern.finditer(logtxt):
        runtime_steps.append(
            {
                "step": int(match.group(1)),
                "time_s": float(match.group(2)),
                "dt_s": float(match.group(3)),
            }
        )

    observed_step_numbers = sorted({r["step"] for r in runtime_steps})
    observed_dt_values = sorted({r["dt_s"] for r in runtime_steps})
    max_observed_step = max(observed_step_numbers) if observed_step_numbers else 0
    last_runtime_time = max((r["time_s"] for r in runtime_steps), default=math.nan)

    dt_match = bool(runtime_steps) and all(close(r["dt_s"], requested_dt) for r in runtime_steps)
    step_count_match = max_observed_step == expected_steps and observed_step_numbers == list(
        range(1, expected_steps + 1)
    )
    runtime_final_time_match = math.isfinite(last_runtime_time) and close(last_runtime_time, expected_end)

    times = [fval(r, "time") for r in erows if "time" in r]
    times = [x for x in times if math.isfinite(x)]
    last_e_time = max(times) if times else math.nan
    csv_final_time_match = math.isfinite(last_e_time) and close(last_e_time, expected_end)
    final_profile = next(
        (p for p in profiles if p.get("output_step") == expected_steps),
        None,
    )
    final_profile_step_match = final_profile is not None

    runtime_contract_pass = (
        args.runtime_rc == 0
        and dt_match
        and step_count_match
        and runtime_final_time_match
        and final_profile_step_match
        and not failure_tokens
    )

    final_ne_min = (
        final_profile["min_ne_m3"]
        if final_profile is not None
        else (fval(last_e, "n_e_min") if last_e else math.nan)
    )
    final_ne_max = (
        final_profile["max_ne_m3"]
        if final_profile is not None
        else (fval(last_e, "n_e_max") if last_e else math.nan)
    )
    final_phi_min = (
        final_profile["min_phi_V"]
        if final_profile is not None
        else (fval(last_e, "phi_min") if last_e else math.nan)
    )
    final_phi_max = (
        final_profile["max_phi_V"]
        if final_profile is not None
        else (fval(last_e, "phi_max") if last_e else math.nan)
    )

    summary = {
        "ne0_m3": ne0,
        "tau_dielectric_s": tau,
        "requested_dt_e_s": requested_dt,
        "requested_dt_over_tau": requested_dt / tau,
        "expected_electron_steps": expected_steps,
        "expected_end_time_s": expected_end,
        "runtime_rc": args.runtime_rc,
        "runtime_step_records": runtime_steps,
        "observed_step_numbers": observed_step_numbers,
        "max_observed_step": max_observed_step,
        "observed_dt_values_s": observed_dt_values,
        "last_runtime_time_s": last_runtime_time,
        "last_converged_electron_time_s": last_e_time,
        "runtime_dt_match": dt_match,
        "runtime_step_count_match": step_count_match,
        "runtime_final_time_match": runtime_final_time_match,
        "csv_final_time_match": csv_final_time_match,
        "final_profile_step_match": final_profile_step_match,
        "runtime_contract_pass": runtime_contract_pass,
        "electron_rows": len(erows),
        "parent_rows": len(prows),
        "last_n_e_min_m3": final_ne_min,
        "last_n_e_max_m3": final_ne_max,
        "last_phi_min_V": final_phi_min,
        "last_phi_max_V": final_phi_max,
        "failure_tokens": failure_tokens,
        "profile_count": len(profiles),
        "profiles": profiles,
        "science_claim": False,
        "claim_scope": "fixed-density dt-over-relaxation-time discriminator",
    }
    out = ROOT / "density_scan_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if not runtime_contract_pass:
        raise SystemExit(
            "runtime contract failed: requested dt / fixed-horizon step contract or final profile was not preserved"
        )


if __name__ == "__main__":
    main()
