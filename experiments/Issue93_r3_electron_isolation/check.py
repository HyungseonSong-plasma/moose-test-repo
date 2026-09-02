#!/usr/bin/env python3
"""Checker for the Issue #93 J1 uniform frozen-heavy electron invariant."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

N0 = 1.0e16
REL_TOL = 1.0e-8
TIME_TOL = 1.0e-18


class CheckError(RuntimeError):
    pass


def _f(row: dict[str, str], key: str) -> float:
    if key not in row:
        raise CheckError(f"missing CSV column: {key}")
    value = float(row[key])
    if not math.isfinite(value):
        raise CheckError(f"nonfinite {key}: {value}")
    return value


def check_csv(path: Path, n0: float = N0, rel_tol: float = REL_TOL) -> dict[str, Any]:
    if not path.is_file():
        raise CheckError(f"CSV does not exist: {path}")
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise CheckError("CSV has no data rows")

    physical = [r for r in rows if _f(r, "time") > TIME_TOL]
    if not physical:
        raise CheckError("CSV has no positive-time physical row")
    row = physical[-1]
    t = _f(row, "time")
    avg = _f(row, "n_e_avg")
    nmin = _f(row, "n_e_min")
    nmax = _f(row, "n_e_max")
    inventory = _f(row, "n_e_inventory")
    volume = _f(row, "carrier_one_integral")
    mobility = _f(row, "electron_mobility_avg")
    diffusion = _f(row, "electron_diffusion_avg")
    if volume <= 0 or mobility <= 0 or diffusion <= 0:
        raise CheckError("volume and electron transport coefficients must be positive")
    expected_inventory = n0 * volume
    inv_rel = abs(inventory - expected_inventory) / expected_inventory
    state_rel = max(abs(avg - n0), abs(nmin - n0), abs(nmax - n0)) / n0
    spread_rel = abs(nmax - nmin) / n0
    passed = inv_rel <= rel_tol and state_rel <= rel_tol and spread_rel <= rel_tol and nmin > 0
    return {
        "issue": 93,
        "check": "J1_FROZEN_HEAVY_ELECTRON_INVARIANT",
        "source_rows": len(rows),
        "physical_rows": len(physical),
        "time_s": t,
        "n0_m3": n0,
        "n_e_avg_m3": avg,
        "n_e_min_m3": nmin,
        "n_e_max_m3": nmax,
        "inventory": inventory,
        "domain_volume": volume,
        "expected_inventory": expected_inventory,
        "inventory_rel_error": inv_rel,
        "state_rel_error": state_rel,
        "spread_rel": spread_rel,
        "electron_mobility_m2_Vs": mobility,
        "electron_diffusion_m2_s": diffusion,
        "rel_tol": rel_tol,
        "pass": passed,
        "scientific_acceptance_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--n0", type=float, default=N0)
    parser.add_argument("--rel-tol", type=float, default=REL_TOL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = check_csv(args.csv, args.n0, args.rel_tol)
    except (CheckError, OSError, ValueError) as exc:
        print(f"ISSUE93_J1_CHECK_ERROR: {exc}")
        return 2
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n")
    print(text)
    print(f"ISSUE93_J1_CHECK: {'PASS' if report['pass'] else 'FAIL'}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
