#!/usr/bin/env python3
"""Analyze Issue #3 D3 combined ion + primary-electron charge conservation."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

E_CHARGE = 1.602176634e-19
ELECTRON_MASS = 9.1095e-31
R_GAS = 8.31446261815324
T_GAS = 300.0
ION_MOLAR_MASS = 0.032
MEAN_ENERGY_EV = 3.0
N_I0 = 1.0e16
N_E0 = 9414771885720.256
DT = 1.0e-7
VOLUME = 1.0
AREA = 1.0
REL_TOL = 1.0e-8
ABS_TOL = 1.0e-20


def rel_error(actual: float, expected: float) -> float:
    scale = max(abs(expected), ABS_TOL)
    return abs(actual - expected) / scale


def rows(path: Path) -> tuple[dict[str, float], dict[str, float]]:
    with path.open(newline="") as stream:
        raw = list(csv.DictReader(stream))
    parsed = [{k: float(v) for k, v in row.items()} for row in raw]
    initial = [row for row in parsed if abs(row["time"]) <= 1.0e-30]
    final = [row for row in parsed if row["time"] > 0.0]
    if not initial or not final:
        raise RuntimeError(f"expected initial and positive-time rows in {path}")
    return initial[0], final[-1]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze_d3.py <d3_combined_primary.csv>", file=sys.stderr)
        return 2

    initial, final = rows(Path(sys.argv[1]))

    ion_speed = math.sqrt(8.0 * R_GAS * T_GAS / (math.pi * ION_MOLAR_MASS))
    electron_speed = math.sqrt(
        16.0 * E_CHARGE * MEAN_ENERGY_EV /
        (3.0 * math.pi * ELECTRON_MASS)
    )
    k_i = 0.25 * ion_speed * AREA / VOLUME
    k_e = 0.25 * electron_speed * AREA / VOLUME

    ni_analytic = N_I0 / (1.0 + k_i * DT)
    ne_analytic = N_E0 / (1.0 + k_e * DT)
    gamma_i_analytic = 0.25 * ion_speed * ni_analytic
    gamma_e_analytic = 0.25 * electron_speed * ne_analytic
    ion_current_analytic = E_CHARGE * gamma_i_analytic * AREA
    electron_current_analytic = -E_CHARGE * gamma_e_analytic * AREA
    net_current_analytic = ion_current_analytic + electron_current_analytic
    surface_charge_analytic = net_current_analytic * DT
    volume_charge_initial_analytic = E_CHARGE * (N_I0 - N_E0) * VOLUME
    volume_charge_final_analytic = E_CHARGE * (ni_analytic - ne_analytic) * VOLUME
    delta_volume_analytic = volume_charge_final_analytic - volume_charge_initial_analytic

    ni0 = initial["ion_inventory"]
    ne0 = initial["electron_inventory"]
    qv0 = initial["volume_charge"]
    nif = final["ion_inventory"]
    nef = final["electron_inventory"]
    qvf = final["volume_charge"]
    ji = final["ion_current_integral"]
    je = final["electron_current_integral"]
    jnet = final["net_current_integral"]
    qs = final["surface_total_charge"]
    area = final["surface_area"]

    delta_qv = qvf - qv0
    ledger = delta_qv + qs
    ledger_scale = max(abs(delta_qv), abs(qs), ABS_TOL)

    checks = {
        "initial_ion_inventory_matches": rel_error(ni0, N_I0) <= REL_TOL,
        "initial_electron_inventory_matches": rel_error(ne0, N_E0) <= REL_TOL,
        "final_ion_inventory_matches_implicit_analytic": rel_error(nif, ni_analytic) <= REL_TOL,
        "final_electron_inventory_matches_implicit_analytic": rel_error(nef, ne_analytic) <= REL_TOL,
        "ion_current_positive": ji > 0.0,
        "electron_current_negative": je < 0.0,
        "component_current_sum_matches_net": rel_error(jnet, ji + je) <= REL_TOL,
        "ion_current_matches_analytic": rel_error(ji, ion_current_analytic) <= REL_TOL,
        "electron_current_matches_analytic": rel_error(je, electron_current_analytic) <= REL_TOL,
        "net_current_matches_analytic": rel_error(jnet, net_current_analytic) <= REL_TOL,
        "surface_charge_matches_net_current_dt": rel_error(qs, jnet * DT) <= REL_TOL,
        "surface_charge_matches_analytic": rel_error(qs, surface_charge_analytic) <= REL_TOL,
        "volume_delta_matches_analytic": rel_error(delta_qv, delta_volume_analytic) <= REL_TOL,
        "global_charge_ledger_closes": abs(ledger) / ledger_scale <= REL_TOL,
        "surface_area_is_one": rel_error(area, AREA) <= REL_TOL,
    }

    result = {
        "classification": "D3_COMBINED_PRIMARY_PASS" if all(checks.values()) else "D3_COMBINED_PRIMARY_FAIL",
        "checks": checks,
        "measured": {
            "ion_inventory_initial": ni0,
            "ion_inventory_final": nif,
            "electron_inventory_initial": ne0,
            "electron_inventory_final": nef,
            "volume_charge_initial_C": qv0,
            "volume_charge_final_C": qvf,
            "delta_volume_charge_C": delta_qv,
            "ion_current_A": ji,
            "electron_current_A": je,
            "net_current_A": jnet,
            "surface_charge_C": qs,
            "surface_area_m2": area,
            "global_ledger_C": ledger,
        },
        "analytic": {
            "ion_thermal_speed_m_s": ion_speed,
            "electron_mean_speed_m_s": electron_speed,
            "ion_inventory_final": ni_analytic,
            "electron_inventory_final": ne_analytic,
            "ion_current_A": ion_current_analytic,
            "electron_current_A": electron_current_analytic,
            "net_current_A": net_current_analytic,
            "surface_charge_C": surface_charge_analytic,
            "delta_volume_charge_C": delta_volume_analytic,
            "global_ledger_C": delta_volume_analytic + surface_charge_analytic,
        },
        "relative_errors": {
            "ion_inventory_final": rel_error(nif, ni_analytic),
            "electron_inventory_final": rel_error(nef, ne_analytic),
            "ion_current": rel_error(ji, ion_current_analytic),
            "electron_current": rel_error(je, electron_current_analytic),
            "net_current": rel_error(jnet, net_current_analytic),
            "surface_charge": rel_error(qs, surface_charge_analytic),
            "volume_delta": rel_error(delta_qv, delta_volume_analytic),
            "global_ledger_scaled": abs(ledger) / ledger_scale,
        },
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
