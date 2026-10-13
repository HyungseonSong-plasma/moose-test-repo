#!/usr/bin/env python3
"""Analyze redesigned Issue #3 lower-D zero/finite dielectric SEE controls."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

E = 1.602176634e-19
R = 8.31446261815324
M_ION = 0.032
T_G = 300.0
M_E_PARTICLE = 9.1095e-31
M_E_ENERGY = 9.1093837139e-31
MEAN_E = 3.0
SEE_E = 4.0
N_I0 = 1.0e16
N_E0 = 9414771885720.256
W0 = N_E0 * MEAN_E
DT = 1.0e-7
REL_TOL = 2.0e-8
ABS = 1.0e-20


def err(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), ABS)


def read(path: Path) -> tuple[dict[str, float], dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(handle)]
    initial = [r for r in rows if abs(r["time"]) <= 1.0e-30]
    final = [r for r in rows if r["time"] > 0.0]
    if not initial or not final:
        raise RuntimeError(f"expected initial/final rows in {path}")
    return initial[0], final[-1]


def analytic(gamma: float) -> dict[str, float]:
    vi = math.sqrt(8.0 * R * T_G / (math.pi * M_ION))
    ve = math.sqrt(16.0 * E * MEAN_E / (3.0 * math.pi * M_E_PARTICLE))
    ve_energy = math.sqrt(16.0 * E * MEAN_E / (3.0 * math.pi * M_E_ENERGY))
    ai = 0.25 * vi
    ae = 0.25 * ve
    beta_w = (5.0 / 6.0) * ve_energy

    ni = N_I0 / (1.0 + ai * DT)
    gi = ai * ni
    gsee = gamma * gi
    ne = (N_E0 + DT * gsee) / (1.0 + ae * DT)
    ge = ae * ne

    signed_e = ge - gsee
    j = E * (gi - signed_e)
    sigma = j * DT

    qv0 = E * (N_I0 - N_E0)
    qvf = E * (ni - ne)
    dqv = qvf - qv0

    w = (W0 + DT * SEE_E * gsee) / (1.0 + beta_w * DT)
    return {
        "ion_inventory": ni,
        "electron_inventory": ne,
        "energy_inventory": w,
        "ion_flux": gi,
        "electron_primary_flux": ge,
        "see_flux": gsee,
        "signed_electron_flux": signed_e,
        "ion_current": E * gi,
        "electron_primary_current": -E * ge,
        "see_current": E * gsee,
        "net_current": j,
        "surface_charge": sigma,
        "delta_volume_charge": dqv,
        "energy_speed": ve_energy,
    }


def evaluate(path: Path, gamma: float) -> dict[str, object]:
    first, last = read(path)
    a = analytic(gamma)

    ni0 = first["ion_inventory"]
    ne0 = first["electron_inventory"]
    w0 = first["energy_inventory"]
    q0 = first["volume_charge"]
    sig0 = first["surface_charge"]

    ni = last["ion_inventory"]
    ne = last["electron_inventory"]
    w = last["energy_inventory"]
    q = last["volume_charge"]
    ji = last["ion_current_integral"]
    je = last["electron_current_integral"]
    gsee = last["see_number_flux_integral"]
    jsee = last["see_current_integral"]
    jnet = last["net_current_integral"]
    sigma = last["surface_charge"]

    dq = q - q0
    charge_ledger = dq + sigma
    gamma_e = -je / E
    particle_ledger = (ne - ne0) + DT * (gamma_e - gsee)
    thermal_w_flux = (5.0 / 6.0) * a["energy_speed"] * w
    energy_ledger = (w - w0) + DT * (thermal_w_flux - SEE_E * gsee)

    cscale = max(abs(dq), abs(sigma), ABS)
    pscale = max(abs(ne-ne0), abs(DT*gamma_e), ABS)
    escale = max(abs(w-w0), abs(DT*thermal_w_flux), ABS)

    checks = {
        "initial_ion": err(ni0, N_I0) <= REL_TOL,
        "initial_electron": err(ne0, N_E0) <= REL_TOL,
        "initial_energy": err(w0, W0) <= REL_TOL,
        "initial_sigma_zero": abs(sig0) <= 1.0e-18,
        "final_ion": err(ni, a["ion_inventory"]) <= REL_TOL,
        "final_electron": err(ne, a["electron_inventory"]) <= REL_TOL,
        "final_energy": err(w, a["energy_inventory"]) <= REL_TOL,
        "ion_current": err(ji, a["ion_current"]) <= REL_TOL,
        "electron_primary_current": err(je, a["electron_primary_current"]) <= REL_TOL,
        "see_flux": err(gsee, a["see_flux"]) <= REL_TOL if gamma else abs(gsee) <= 1.0e-12,
        "see_current": err(jsee, a["see_current"]) <= REL_TOL if gamma else abs(jsee) <= 1.0e-18,
        "net_current": err(jnet, a["net_current"]) <= REL_TOL,
        "surface_charge_current_dt": err(sigma, jnet * DT) <= REL_TOL,
        "surface_charge": err(sigma, a["surface_charge"]) <= REL_TOL,
        "volume_charge_delta": err(dq, a["delta_volume_charge"]) <= REL_TOL,
        "global_charge_ledger": abs(charge_ledger) / cscale <= REL_TOL,
        "electron_particle_ledger": abs(particle_ledger) / pscale <= REL_TOL,
        "electron_energy_ledger": abs(energy_ledger) / escale <= REL_TOL,
    }

    return {
        "gamma": gamma,
        "analytic": a,
        "measured": {
            "ion_inventory": ni,
            "electron_inventory": ne,
            "energy_inventory_eV_m3": w,
            "ion_current_A": ji,
            "electron_primary_current_A": je,
            "see_flux_s-1": gsee,
            "see_current_A": jsee,
            "net_current_A": jnet,
            "surface_charge_C": sigma,
            "delta_volume_charge_C": dq,
            "charge_ledger_C": charge_ledger,
            "particle_ledger": particle_ledger,
            "energy_ledger_eV": energy_ledger,
        },
        "scaled_errors": {
            "charge": abs(charge_ledger) / cscale,
            "particle": abs(particle_ledger) / pscale,
            "energy": abs(energy_ledger) / escale,
        },
        "checks": checks,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: analyze_d4_lowerd.py <see_off.csv> <see_on.csv>", file=sys.stderr)
        return 2

    off = evaluate(Path(sys.argv[1]), 0.0)
    on = evaluate(Path(sys.argv[2]), 0.05)

    cross = {
        "finite_see_flux_positive": on["measured"]["see_flux_s-1"] > 0.0,
        "finite_see_current_positive": on["measured"]["see_current_A"] > 0.0,
        "see_increases_electron_inventory": on["measured"]["electron_inventory"] > off["measured"]["electron_inventory"],
        "see_increases_electron_energy": on["measured"]["energy_inventory_eV_m3"] > off["measured"]["energy_inventory_eV_m3"],
        "see_shifts_sigma_positive": on["measured"]["surface_charge_C"] > off["measured"]["surface_charge_C"],
    }

    passed = all(off["checks"].values()) and all(on["checks"].values()) and all(cross.values())
    report = {
        "classification": "D4_LOWERD_DIELECTRIC_SEE_PASS" if passed else "D4_LOWERD_DIELECTRIC_SEE_FAIL",
        "coefficient_scope": "gamma=0.05 and emitted-electron energy=4 eV are controlled verification values",
        "see_off": off,
        "see_on": on,
        "cross_checks": cross,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
