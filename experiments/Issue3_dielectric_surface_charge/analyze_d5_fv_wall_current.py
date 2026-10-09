#!/usr/bin/env python3
"""Analytic acceptance checks for the canonical FV-current/lower-D sigma_s path."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

NA = 6.02214076e23
E = 1.602176634e-19
EPS0 = 8.8541878128e-12
R = 8.31446261815324
PI = math.pi
M_ION = 0.032
M_E = 9.1095e-31
T_G = 300.0
MEAN_E = 3.0
N0 = 1.0e12
DT = 1.0e-9
EPS_P = 1.0
EPS_D = 4.0

REL_TOL = 5.0e-8
ABS_Q = 1.0e-18
ABS_N = 1.0e-3
ABS_PHI = 1.0e-8


def rel_close(a: float, b: float, atol: float = 0.0) -> bool:
    return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=atol)


def analytic() -> dict[str, float]:
    vi = math.sqrt(8.0 * R * T_G / (PI * M_ION))
    ve = math.sqrt(16.0 * E * MEAN_E / (3.0 * PI * M_E))
    ki = 0.25 * vi
    ke = 0.25 * ve

    ni = N0 / (1.0 + ki * DT)
    ne = N0 / (1.0 + ke * DT)
    gi = ki * ni
    ge = ke * ne
    j = E * (gi - ge)
    sigma = j * DT
    rho = E * (ni - ne)
    delta_q_volume = rho  # unit plasma volume, initially neutral
    ledger = delta_q_volume + sigma  # unit interface area

    # Unit plasma/dielectric layer lengths with grounded outer ends.
    # Plasma has constant source S=rho/eps0 and dielectric has zero volume charge.
    S = rho / EPS0
    A = (sigma / EPS0 + S * (1.0 + EPS_D / (2.0 * EPS_P))) / (EPS_P + EPS_D)
    phi_interface = -S / (2.0 * EPS_P) + A

    return {
        "ion_speed_m_s": vi,
        "electron_speed_m_s": ve,
        "ion_final_inventory": ni,
        "electron_final_inventory": ne,
        "ion_flux_m2_s": gi,
        "electron_flux_m2_s": ge,
        "net_surface_current_A_m2": j,
        "sigma_C_m2": sigma,
        "volume_charge_C": rho,
        "global_ledger_C": ledger,
        "phi_interface_V": phi_interface,
    }


def main() -> int:
    csv_path = Path(sys.argv[1] if len(sys.argv) > 1 else "d5_fv_wall_current_feedback_out.csv")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        raise RuntimeError(f"expected INITIAL and TIMESTEP_END rows in {csv_path}")

    first, last = rows[0], rows[-1]
    a = analytic()

    ni0 = float(first["ion_inventory"])
    ne0 = float(first["electron_inventory"])
    qv0 = float(first["volume_charge"])
    sig0 = float(first["sigma_average"])

    ni = float(last["ion_inventory"])
    ne = float(last["electron_inventory"])
    qv = float(last["volume_charge"])
    j = float(last["net_surface_current"])
    sig = float(last["sigma_average"])
    phi = float(last["phi_interface"])

    delta_qv = qv - qv0
    ledger = delta_qv + sig

    checks = {
        "initial_neutrality": rel_close(ni0, N0, ABS_N) and rel_close(ne0, N0, ABS_N) and abs(qv0) <= ABS_Q,
        "initial_surface_charge_zero": abs(sig0) <= ABS_Q,
        "ion_inventory_backward_euler": rel_close(ni, a["ion_final_inventory"], ABS_N),
        "electron_inventory_backward_euler": rel_close(ne, a["electron_final_inventory"], ABS_N),
        "surface_current_matches_fluxes": rel_close(j, a["net_surface_current_A_m2"], ABS_Q),
        "sigma_matches_current_dt": rel_close(sig, j * DT, ABS_Q),
        "sigma_matches_analytic": rel_close(sig, a["sigma_C_m2"], ABS_Q),
        "volume_charge_matches_analytic": rel_close(delta_qv, a["volume_charge_C"], ABS_Q),
        "global_charge_ledger": abs(ledger) <= 2.0e-16,
        "poisson_interface_matches_volume_plus_surface": rel_close(phi, a["phi_interface_V"], ABS_PHI),
    }

    report = {
        "analytic": a,
        "measured": {
            "initial_ion_inventory": ni0,
            "initial_electron_inventory": ne0,
            "final_ion_inventory": ni,
            "final_electron_inventory": ne,
            "delta_volume_charge_C": delta_qv,
            "net_surface_current_A_m2": j,
            "sigma_C_m2": sig,
            "global_ledger_C": ledger,
            "phi_interface_V": phi,
        },
        "checks": checks,
        "classification": "D5_FV_WALL_CURRENT_FEEDBACK_PASS" if all(checks.values()) else "D5_FV_WALL_CURRENT_FEEDBACK_FAIL",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
