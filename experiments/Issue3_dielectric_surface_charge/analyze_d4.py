#!/usr/bin/env python3
"""Analyze Issue #3 D4 zero/finite dielectric SEE controls."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

E_CHARGE = 1.602176634e-19
R_GAS = 8.31446261815324
ION_MOLAR_MASS = 0.032
T_GAS = 300.0
PARTICLE_ELECTRON_MASS = 9.1095e-31
ENERGY_BC_ELECTRON_MASS = 9.1093837139e-31
MEAN_ENERGY_EV = 3.0
SEE_ENERGY_EV = 4.0
N_I0 = 1.0e16
N_E0 = 9414771885720.256
ENERGY0 = N_E0 * MEAN_ENERGY_EV
DT = 1.0e-7
AREA = 1.0
VOLUME = 1.0
REL_TOL = 2.0e-8
ABS_TOL = 1.0e-20


def rel_error(actual: float, expected: float) -> float:
    return abs(actual - expected) / max(abs(expected), ABS_TOL)


def initial_final(path: Path) -> tuple[dict[str, float], dict[str, float]]:
    with path.open(newline="") as stream:
        raw = list(csv.DictReader(stream))
    rows = [{key: float(value) for key, value in row.items()} for row in raw]
    initial = [row for row in rows if abs(row["time"]) <= 1.0e-30]
    final = [row for row in rows if row["time"] > 0.0]
    if not initial or not final:
        raise RuntimeError(f"expected initial and final rows in {path}")
    return initial[0], final[-1]


def analytic(gamma: float) -> dict[str, float]:
    ion_speed = math.sqrt(8.0 * R_GAS * T_GAS / (math.pi * ION_MOLAR_MASS))
    electron_speed = math.sqrt(
        16.0 * E_CHARGE * MEAN_ENERGY_EV /
        (3.0 * math.pi * PARTICLE_ELECTRON_MASS)
    )
    energy_speed = math.sqrt(
        16.0 * E_CHARGE * MEAN_ENERGY_EV /
        (3.0 * math.pi * ENERGY_BC_ELECTRON_MASS)
    )

    alpha_i = 0.25 * ion_speed * AREA / VOLUME
    alpha_e = 0.25 * electron_speed * AREA / VOLUME
    energy_beta = (5.0 / 6.0) * energy_speed * AREA / VOLUME

    ni = N_I0 / (1.0 + alpha_i * DT)
    gamma_i = 0.25 * ion_speed * ni
    gamma_see = gamma * gamma_i
    ne = (N_E0 + DT * gamma_see * AREA / VOLUME) / (1.0 + alpha_e * DT)
    gamma_e = 0.25 * electron_speed * ne

    ji = E_CHARGE * gamma_i * AREA
    je = -E_CHARGE * gamma_e * AREA
    jsee = E_CHARGE * gamma_see * AREA
    jnet = ji + je + jsee
    surface_charge = jnet * DT

    qv0 = E_CHARGE * (N_I0 - N_E0) * VOLUME
    qvf = E_CHARGE * (ni - ne) * VOLUME
    delta_qv = qvf - qv0

    energy = (
        ENERGY0 + DT * SEE_ENERGY_EV * gamma_see * AREA / VOLUME
    ) / (1.0 + energy_beta * DT)
    thermal_energy_flux = (5.0 / 6.0) * energy_speed * energy
    see_energy_flux = SEE_ENERGY_EV * gamma_see

    return {
        "gamma": gamma,
        "ion_speed": ion_speed,
        "electron_speed": electron_speed,
        "energy_speed": energy_speed,
        "ion_inventory": ni,
        "electron_inventory": ne,
        "energy_inventory": energy,
        "ion_flux": gamma_i,
        "electron_flux": gamma_e,
        "see_flux": gamma_see,
        "ion_current": ji,
        "electron_current": je,
        "see_current": jsee,
        "net_current": jnet,
        "surface_charge": surface_charge,
        "delta_volume_charge": delta_qv,
        "thermal_energy_flux": thermal_energy_flux,
        "see_energy_flux": see_energy_flux,
    }


def evaluate(path: Path, gamma: float) -> dict[str, object]:
    initial, final = initial_final(path)
    ref = analytic(gamma)

    ni0 = initial["ion_inventory"]
    ne0 = initial["electron_inventory"]
    w0 = initial["energy_inventory"]
    qv0 = initial["volume_charge"]

    ni = final["ion_inventory"]
    ne = final["electron_inventory"]
    energy = final["energy_inventory"]
    qv = final["volume_charge"]
    ji = final["ion_current_integral"]
    je = final["electron_current_integral"]
    see_flux = final["see_number_flux_integral"]
    jsee = final["see_current_integral"]
    jnet = final["net_current_integral"]
    qs = final["surface_total_charge"]
    area = final["surface_area"]

    delta_qv = qv - qv0
    charge_ledger = delta_qv + qs
    charge_scale = max(abs(delta_qv), abs(qs), ABS_TOL)

    gamma_i_from_current = ji / E_CHARGE
    gamma_e_from_current = -je / E_CHARGE
    particle_ledger = (ne - ne0) + DT * (gamma_e_from_current - see_flux)
    particle_scale = max(abs(ne - ne0), abs(DT * gamma_e_from_current), ABS_TOL)

    thermal_energy_flux = (5.0 / 6.0) * ref["energy_speed"] * energy
    see_energy_flux = SEE_ENERGY_EV * see_flux
    energy_ledger = (energy - w0) + DT * (thermal_energy_flux - see_energy_flux)
    energy_scale = max(abs(energy - w0), abs(DT * thermal_energy_flux), ABS_TOL)

    checks = {
        "initial_ion_inventory_matches": rel_error(ni0, N_I0) <= REL_TOL,
        "initial_electron_inventory_matches": rel_error(ne0, N_E0) <= REL_TOL,
        "initial_energy_inventory_matches": rel_error(w0, ENERGY0) <= REL_TOL,
        "final_ion_inventory_matches": rel_error(ni, ref["ion_inventory"]) <= REL_TOL,
        "final_electron_inventory_matches": rel_error(ne, ref["electron_inventory"]) <= REL_TOL,
        "final_energy_inventory_matches": rel_error(energy, ref["energy_inventory"]) <= REL_TOL,
        "ion_current_matches": rel_error(ji, ref["ion_current"]) <= REL_TOL,
        "electron_current_matches": rel_error(je, ref["electron_current"]) <= REL_TOL,
        "see_flux_matches_gamma_ion_flux": rel_error(see_flux, ref["see_flux"]) <= REL_TOL,
        "see_current_matches": rel_error(jsee, ref["see_current"]) <= REL_TOL,
        "component_current_sum_matches_net": rel_error(jnet, ji + je + jsee) <= REL_TOL,
        "net_current_matches": rel_error(jnet, ref["net_current"]) <= REL_TOL,
        "surface_charge_matches_current_dt": rel_error(qs, jnet * DT) <= REL_TOL,
        "surface_charge_matches": rel_error(qs, ref["surface_charge"]) <= REL_TOL,
        "volume_charge_delta_matches": rel_error(delta_qv, ref["delta_volume_charge"]) <= REL_TOL,
        "global_charge_ledger_closes": abs(charge_ledger) / charge_scale <= REL_TOL,
        "electron_particle_ledger_closes": abs(particle_ledger) / particle_scale <= REL_TOL,
        "electron_energy_ledger_closes": abs(energy_ledger) / energy_scale <= REL_TOL,
        "surface_area_is_one": rel_error(area, AREA) <= REL_TOL,
    }

    return {
        "gamma": gamma,
        "checks": checks,
        "measured": {
            "ion_inventory_initial": ni0,
            "ion_inventory_final": ni,
            "electron_inventory_initial": ne0,
            "electron_inventory_final": ne,
            "energy_inventory_initial_eV": w0,
            "energy_inventory_final_eV": energy,
            "delta_volume_charge_C": delta_qv,
            "ion_current_A": ji,
            "electron_current_A": je,
            "see_number_flux_s-1": see_flux,
            "see_current_A": jsee,
            "net_current_A": jnet,
            "surface_charge_C": qs,
            "charge_ledger_C": charge_ledger,
            "electron_particle_ledger": particle_ledger,
            "electron_energy_ledger_eV": energy_ledger,
        },
        "analytic": ref,
        "scaled_errors": {
            "charge_ledger": abs(charge_ledger) / charge_scale,
            "electron_particle_ledger": abs(particle_ledger) / particle_scale,
            "electron_energy_ledger": abs(energy_ledger) / energy_scale,
        },
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: analyze_d4.py <see_off.csv> <see_on.csv>", file=sys.stderr)
        return 2

    off = evaluate(Path(sys.argv[1]), 0.0)
    on = evaluate(Path(sys.argv[2]), 0.05)

    off_m = off["measured"]
    on_m = on["measured"]
    on_ref = on["analytic"]

    cross_checks = {
        "zero_see_control_is_zero": abs(float(off_m["see_number_flux_s-1"])) <= 1.0e-12,
        "finite_see_flux_positive": float(on_m["see_number_flux_s-1"]) > 0.0,
        "finite_see_current_positive": float(on_m["see_current_A"]) > 0.0,
        "finite_see_ratio_is_0p05": rel_error(
            float(on_m["see_number_flux_s-1"]), float(on_ref["see_flux"])
        ) <= REL_TOL,
        "see_increases_electron_inventory": (
            float(on_m["electron_inventory_final"]) > float(off_m["electron_inventory_final"])
        ),
        "see_increases_electron_energy": (
            float(on_m["energy_inventory_final_eV"]) > float(off_m["energy_inventory_final_eV"])
        ),
        "see_shifts_surface_charge_positive": (
            float(on_m["surface_charge_C"]) > float(off_m["surface_charge_C"])
        ),
    }

    all_checks = (
        all(bool(v) for v in off["checks"].values())
        and all(bool(v) for v in on["checks"].values())
        and all(cross_checks.values())
    )

    result = {
        "classification": "D4_DIELECTRIC_SEE_PASS" if all_checks else "D4_DIELECTRIC_SEE_FAIL",
        "coefficient_scope": (
            "gamma=0.05 and 4 eV are controlled inherited oxygen-ICP discriminator values; "
            "they are not asserted as universal dielectric material parameters"
        ),
        "see_off": off,
        "see_on": on,
        "cross_checks": cross_checks,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all_checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
