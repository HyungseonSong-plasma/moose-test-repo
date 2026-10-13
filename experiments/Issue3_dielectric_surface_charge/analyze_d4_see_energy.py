#!/usr/bin/env python3
"""Analyze isolated Issue #3 dielectric SEE electron-energy controls."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

E_CHARGE = 1.602176634e-19
M_E = 9.1093837139e-31
MEAN_E = 3.0
SEE_E = 4.0
W0 = 1.0e16
DT = 1.0e-7
GSEE_OFF = 0.0
GSEE_ON = 1.0e21
REL_TOL = 5.0e-8


def read(path: Path) -> tuple[float, float]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(handle)]
    if len(rows) < 2:
        raise RuntimeError(f"expected INITIAL and TIMESTEP_END rows in {path}")
    return rows[0]["energy_inventory"], rows[-1]["energy_inventory"]


def analytic(gsee: float) -> dict[str, float]:
    speed = math.sqrt(16.0 * E_CHARGE * MEAN_E / (3.0 * math.pi * M_E))
    beta = (5.0 / 6.0) * speed
    wf = (W0 + DT * SEE_E * gsee) / (1.0 + beta * DT)
    thermal_flux = beta * wf
    see_energy_flux = SEE_E * gsee
    ledger = (wf - W0) + DT * (thermal_flux - see_energy_flux)
    return {
        "mean_speed_m_s": speed,
        "thermal_loss_rate_m_s": beta,
        "see_number_flux_m2_s": gsee,
        "see_energy_flux_eV_m2_s": see_energy_flux,
        "final_energy_inventory_eV_m3": wf,
        "energy_ledger_eV_m3": ledger,
    }


def evaluate(path: Path, gsee: float) -> dict[str, object]:
    w_initial, w_final = read(path)
    a = analytic(gsee)
    thermal_flux = a["thermal_loss_rate_m_s"] * w_final
    ledger = (w_final - w_initial) + DT * (thermal_flux - SEE_E * gsee)
    scale = max(abs(w_final - w_initial), abs(DT * thermal_flux), abs(DT * SEE_E * gsee), 1.0)
    checks = {
        "initial_energy": math.isclose(w_initial, W0, rel_tol=REL_TOL),
        "final_energy_backward_euler": math.isclose(
            w_final, a["final_energy_inventory_eV_m3"], rel_tol=REL_TOL
        ),
        "energy_ledger": abs(ledger) / scale <= REL_TOL,
    }
    return {
        "analytic": a,
        "measured": {
            "initial_energy_inventory_eV_m3": w_initial,
            "final_energy_inventory_eV_m3": w_final,
            "energy_ledger_eV_m3": ledger,
        },
        "checks": checks,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: analyze_d4_see_energy.py <see_off.csv> <see_on.csv>", file=sys.stderr)
        return 2

    off = evaluate(Path(sys.argv[1]), GSEE_OFF)
    on = evaluate(Path(sys.argv[2]), GSEE_ON)
    expected_shift = (
        analytic(GSEE_ON)["final_energy_inventory_eV_m3"]
        - analytic(GSEE_OFF)["final_energy_inventory_eV_m3"]
    )
    measured_shift = (
        on["measured"]["final_energy_inventory_eV_m3"]
        - off["measured"]["final_energy_inventory_eV_m3"]
    )
    cross = {
        "see_increases_electron_energy": measured_shift > 0.0,
        "see_energy_shift_matches_analytic": math.isclose(
            measured_shift, expected_shift, rel_tol=REL_TOL
        ),
    }
    passed = all(off["checks"].values()) and all(on["checks"].values()) and all(cross.values())
    report = {
        "classification": "D4_DIELECTRIC_SEE_ENERGY_PASS" if passed else "D4_DIELECTRIC_SEE_ENERGY_FAIL",
        "scope": "isolated physical_eV wall-energy equation; SEE emitted energy fixed by PhysicsFVElectronEnergyWallFluxBC at 4 eV",
        "see_off": off,
        "see_on": on,
        "expected_energy_shift_eV_m3": expected_shift,
        "measured_energy_shift_eV_m3": measured_shift,
        "cross_checks": cross,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
