#!/usr/bin/env python3
"""Analyze compact Issue #3 lower-D zero/finite dielectric SEE charge controls."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

E = 1.602176634e-19
EPS0 = 8.8541878128e-12
R = 8.31446261815324
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


def close(a: float, b: float, atol: float = 0.0) -> bool:
    return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=atol)


def analytic(gamma: float) -> dict[str, float]:
    vi = math.sqrt(8.0 * R * T_G / (math.pi * M_ION))
    ve = math.sqrt(16.0 * E * MEAN_E / (3.0 * math.pi * M_E))
    ki = 0.25 * vi
    ke = 0.25 * ve

    ni = N0 / (1.0 + ki * DT)
    gi = ki * ni
    gsee = gamma * gi
    ne = (N0 + DT * gsee) / (1.0 + ke * DT)
    ge_primary = ke * ne
    ge_signed = ge_primary - gsee

    j = E * (gi - ge_signed)
    sigma = j * DT
    rho = E * (ni - ne)
    ledger = rho + sigma

    # Grounded unit plasma and dielectric layers. Plasma has uniform rho;
    # dielectric has no volume charge. This is the same analytic weak-form
    # solution used by the D5 volume+surface discriminator.
    S = rho / EPS0
    A = (sigma / EPS0 + S * (1.0 + EPS_D / (2.0 * EPS_P))) / (EPS_P + EPS_D)
    phi_interface = -S / (2.0 * EPS_P) + A

    return {
        "ion_inventory": ni,
        "electron_inventory": ne,
        "ion_flux": gi,
        "electron_primary_flux": ge_primary,
        "see_flux": gsee,
        "electron_signed_flux": ge_signed,
        "see_current": E * gsee,
        "net_surface_current": j,
        "surface_charge": sigma,
        "volume_charge": rho,
        "global_ledger": ledger,
        "phi_interface": phi_interface,
    }


def read(path: Path) -> tuple[dict[str, float], dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(handle)]
    if len(rows) < 2:
        raise RuntimeError(f"expected INITIAL and TIMESTEP_END rows in {path}")
    return rows[0], rows[-1]


def evaluate(path: Path, gamma: float) -> dict[str, object]:
    first, last = read(path)
    a = analytic(gamma)

    ni0 = first["ion_inventory"]
    ne0 = first["electron_inventory"]
    q0 = first["volume_charge"]
    sig0 = first["surface_charge"]
    phi0 = first["phi_interface"]

    ni = last["ion_inventory"]
    ne = last["electron_inventory"]
    q = last["volume_charge"]
    gsee = last["see_number_flux"]
    jsee = last["see_current"]
    j = last["net_surface_current"]
    sigma = last["surface_charge"]
    phi = last["phi_interface"]

    dq = q - q0
    ledger = dq + sigma
    particle_ledger_i = (ni - ni0) + DT * a["ion_flux"]
    particle_ledger_e = (ne - ne0) + DT * a["electron_signed_flux"]

    qscale = max(abs(dq), abs(sigma), ABS_Q)
    niscale = max(abs(ni-ni0), abs(DT*a["ion_flux"]), 1.0)
    nescale = max(abs(ne-ne0), abs(DT*a["electron_signed_flux"]), 1.0)

    checks = {
        "initial_neutrality": close(ni0, N0, ABS_N) and close(ne0, N0, ABS_N) and abs(q0) <= ABS_Q,
        "initial_sigma_zero": abs(sig0) <= ABS_Q,
        "initial_phi_zero": abs(phi0) <= ABS_PHI,
        "ion_inventory": close(ni, a["ion_inventory"], ABS_N),
        "electron_inventory": close(ne, a["electron_inventory"], ABS_N),
        "see_flux": close(gsee, a["see_flux"], 1.0e-8) if gamma else abs(gsee) <= 1.0e-12,
        "see_current": close(jsee, a["see_current"], ABS_Q) if gamma else abs(jsee) <= ABS_Q,
        "net_current": close(j, a["net_surface_current"], ABS_Q),
        "sigma_current_dt": close(sigma, j * DT, ABS_Q),
        "sigma_analytic": close(sigma, a["surface_charge"], ABS_Q),
        "volume_charge": close(dq, a["volume_charge"], ABS_Q),
        "global_charge_ledger": abs(ledger) / qscale <= REL_TOL,
        "ion_particle_ledger": abs(particle_ledger_i) / niscale <= REL_TOL,
        "electron_particle_ledger": abs(particle_ledger_e) / nescale <= REL_TOL,
        "phi_interface": close(phi, a["phi_interface"], ABS_PHI),
    }

    return {
        "gamma": gamma,
        "analytic": a,
        "measured": {
            "ion_inventory": ni,
            "electron_inventory": ne,
            "see_flux": gsee,
            "see_current": jsee,
            "net_surface_current": j,
            "surface_charge": sigma,
            "delta_volume_charge": dq,
            "global_ledger": ledger,
            "phi_interface": phi,
        },
        "checks": checks,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: analyze_d4_lowerd_charge.py <see_off.csv> <see_on.csv>", file=sys.stderr)
        return 2

    off = evaluate(Path(sys.argv[1]), 0.0)
    on = evaluate(Path(sys.argv[2]), 0.05)

    cross = {
        "finite_see_flux_positive": on["measured"]["see_flux"] > 0.0,
        "finite_see_current_positive": on["measured"]["see_current"] > 0.0,
        "see_increases_electron_inventory": on["measured"]["electron_inventory"] > off["measured"]["electron_inventory"],
        "see_shifts_surface_charge_positive": on["measured"]["surface_charge"] > off["measured"]["surface_charge"],
        "see_shifts_interface_potential_positive": on["measured"]["phi_interface"] > off["measured"]["phi_interface"],
    }

    passed = all(off["checks"].values()) and all(on["checks"].values()) and all(cross.values())
    report = {
        "classification": "D4_LOWERD_DIELECTRIC_SEE_CHARGE_PASS" if passed else "D4_LOWERD_DIELECTRIC_SEE_CHARGE_FAIL",
        "coefficient_scope": "gamma=0.05 is a controlled verification coefficient, not a universal dielectric material value",
        "see_off": off,
        "see_on": on,
        "cross_checks": cross,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
