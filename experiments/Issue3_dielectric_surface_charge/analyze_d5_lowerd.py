#!/usr/bin/env python3
"""Acceptance check for the redesigned lower-D surface-charge D5 discriminator."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

EPS0 = 8.8541878128e-12
J_SURFACE = 1.0e-4
DT = 1.0e-7
EPS_PLASMA = 1.0
EPS_DIELECTRIC = 4.0
L_PLASMA = 1.0
L_DIELECTRIC = 1.0

SIGMA_EXPECTED = J_SURFACE * DT
PHI_INTERFACE_EXPECTED = SIGMA_EXPECTED / (
    EPS0 * (EPS_PLASMA / L_PLASMA + EPS_DIELECTRIC / L_DIELECTRIC)
)

REL_TOL = 2.0e-8
ABS_TOL_SIGMA = 1.0e-18
ABS_TOL_PHI = 1.0e-10


def close(measured: float, expected: float, abs_tol: float) -> bool:
    return math.isclose(measured, expected, rel_tol=REL_TOL, abs_tol=abs_tol)


def main() -> int:
    csv_path = Path(sys.argv[1] if len(sys.argv) > 1 else "d5_lowerd_surface_feedback.csv")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) < 2:
        raise RuntimeError(f"expected INITIAL and TIMESTEP_END rows in {csv_path}")

    initial = rows[0]
    final = rows[-1]

    sigma0 = float(initial["sigma_average"])
    sigma = float(final["sigma_average"])
    phi0 = float(initial["phi_interface"])
    phi = float(final["phi_interface"])

    checks = {
        "initial_sigma_zero": abs(sigma0) <= ABS_TOL_SIGMA,
        "initial_phi_zero": abs(phi0) <= ABS_TOL_PHI,
        "sigma_matches_j_dt": close(sigma, SIGMA_EXPECTED, ABS_TOL_SIGMA),
        "phi_matches_surface_jump": close(phi, PHI_INTERFACE_EXPECTED, ABS_TOL_PHI),
        "positive_surface_charge_gives_positive_phi": sigma > 0.0 and phi > 0.0,
    }

    report = {
        "analytic": {
            "surface_current_density_A_m2": J_SURFACE,
            "dt_s": DT,
            "sigma_C_m2": SIGMA_EXPECTED,
            "phi_interface_V": PHI_INTERFACE_EXPECTED,
        },
        "measured": {
            "initial_sigma_C_m2": sigma0,
            "final_sigma_C_m2": sigma,
            "initial_phi_interface_V": phi0,
            "final_phi_interface_V": phi,
        },
        "checks": checks,
        "classification": "D5_LOWERD_SURFACE_FEEDBACK_PASS" if all(checks.values()) else "D5_LOWERD_SURFACE_FEEDBACK_FAIL",
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
