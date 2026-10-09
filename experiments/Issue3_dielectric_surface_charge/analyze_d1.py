#!/usr/bin/env python3
"""Analyze Issue #3 D1 ion-only dielectric surface charging."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

E_CHARGE = 1.602176634e-19
R_GAS = 8.31446261815324
T_GAS = 300.0
MOLAR_MASS = 0.032
N_I = 1.0e16
DT = 1.0e-7
STICKING = 1.0
REL_TOL = 1.0e-10
ABS_TOL = 1.0e-24


def rel_error(actual: float, expected: float) -> float:
    scale = max(abs(expected), ABS_TOL)
    return abs(actual - expected) / scale


def final_positive_row(path: Path) -> dict[str, float]:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))

    physical = [row for row in rows if float(row["time"]) > 0.0]
    if not physical:
        raise RuntimeError(f"no positive-time row in {path}")

    return {key: float(value) for key, value in physical[-1].items()}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze_d1.py <d1_ion_only.csv>", file=sys.stderr)
        return 2

    row = final_positive_row(Path(sys.argv[1]))

    area = row["surface_area"]
    current_integral = row["ion_current_integral"]
    total_charge = row["surface_total_charge"]
    average_charge = row["surface_average_charge"]

    thermal_speed = math.sqrt(
        8.0 * R_GAS * T_GAS / (math.pi * MOLAR_MASS)
    )
    gamma_ion = STICKING * 0.25 * N_I * thermal_speed
    analytic_current_integral = E_CHARGE * gamma_ion * area
    expected_charge_from_runtime_current = current_integral * DT
    analytic_total_charge = analytic_current_integral * DT
    analytic_average_charge = E_CHARGE * gamma_ion * DT

    checks = {
        "positive_ion_current": current_integral > 0.0,
        "positive_surface_charge": total_charge > 0.0,
        "runtime_current_matches_analytic": rel_error(
            current_integral, analytic_current_integral
        ) <= REL_TOL,
        "state_matches_runtime_current_dt": rel_error(
            total_charge, expected_charge_from_runtime_current
        ) <= REL_TOL,
        "state_matches_independent_analytic": rel_error(
            total_charge, analytic_total_charge
        ) <= REL_TOL,
        "average_matches_independent_analytic": rel_error(
            average_charge, analytic_average_charge
        ) <= REL_TOL,
    }

    result = {
        "classification": "D1_ION_ONLY_PASS" if all(checks.values()) else "D1_ION_ONLY_FAIL",
        "checks": checks,
        "measured": {
            "surface_area_m2": area,
            "ion_current_integral_A": current_integral,
            "surface_total_charge_C": total_charge,
            "surface_average_charge_C_m2": average_charge,
        },
        "analytic": {
            "thermal_speed_m_s": thermal_speed,
            "ion_number_flux_m2_s": gamma_ion,
            "ion_current_integral_A": analytic_current_integral,
            "surface_total_charge_C": analytic_total_charge,
            "surface_average_charge_C_m2": analytic_average_charge,
        },
        "relative_errors": {
            "current_vs_analytic": rel_error(
                current_integral, analytic_current_integral
            ),
            "charge_vs_runtime_current_dt": rel_error(
                total_charge, expected_charge_from_runtime_current
            ),
            "charge_vs_analytic": rel_error(total_charge, analytic_total_charge),
            "average_vs_analytic": rel_error(
                average_charge, analytic_average_charge
            ),
        },
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
