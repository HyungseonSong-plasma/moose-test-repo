#!/usr/bin/env python3
"""Issue #243 T1 P3 coupled one-step runtime qualification.

Particle transport/primary-sheath/SEE rates are evaluated in physical-number
units after the log-molar conversion. Electron-energy representation remains
frozen on the accepted normalized basis until T2.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from experiments.Issue217_sheath_energy_closure import run as w45
from experiments.Issue27_surface_reactions.controlled_wall import see as a8
from experiments.historical_recipe_support import issue26_energy_chain as energy
from experiments.historical_recipe_support.issue26_e1 import ENERGY_REFERENCE_EV
from experiments.Issue243_t1_log_molar_coupled_particle import run as t1

ELEMENTARY_CHARGE_C = 1.602176634e-19
AVOGADRO = 6.02214076e23


def _metrics(case_dir: Path, input_text: str, meta: dict[str, Any]) -> dict[str, Any]:
    rows = w45.s5r._read_rows(case_dir / "input_out.csv")
    if len(rows) < 2:
        raise RuntimeError("P3 requires INITIAL and TIMESTEP_END rows")
    initial, final = rows[0], rows[-1]
    dt = w45.s5r._num(final, "time") - w45.s5r._num(initial, "time")
    if dt <= 0.0:
        raise RuntimeError(f"non-positive P3 dt={dt}")

    volume = w45.s5r._num(final, "domain_volume")
    n_ref = float(meta["electron_reference_density_m3"])
    wall = w45._wall_observables(final)

    # T1 particle BCs and particle inventory are already in physical-number units.
    primary_rate = w45._physical(w45.s5r._num(final, w45.PARTICLE_PP))
    see_rate = w45._physical(w45.s5r._num(final, a8.SEE_PP))
    electron_accumulation = (
        w45.s5r._num(final, "n_e_inventory")
        - w45.s5r._num(initial, "n_e_inventory")
    ) / dt
    volumetric_electron_rate = w45.s5r._num(final, "s5r_electron_source_avg") * volume
    expected_electron_rate = volumetric_electron_rate + see_rate - primary_rate
    electron_defect = w45._rel_defect(
        electron_accumulation,
        expected_electron_rate,
        volumetric_electron_rate,
        see_rate,
        primary_rate,
    )

    # Energy remains on the accepted normalized representation in T1.
    coefficients = w45.s5r._energy_coefficients(input_text)
    volumetric_energy_norm_rate = w45.s5r._energy_source_density(final, coefficients) * volume
    energy_accum_norm_rate = (
        w45.s5r._num(final, "s5r_n_epsilon_inventory")
        - w45.s5r._num(initial, "s5r_n_epsilon_inventory")
    ) / dt
    energy_scale = n_ref * ENERGY_REFERENCE_EV * ELEMENTARY_CHARGE_C
    primary_power = w45._physical(w45.s5r._num(final, w45.ENERGY_POWER_PP))
    see_power = w45._physical(w45.s5r._num(final, energy.SEE_ENERGY_COUPLED_POWER_PP))
    expected_energy_norm_rate = (
        volumetric_energy_norm_rate - primary_power / energy_scale + see_power / energy_scale
    )
    energy_defect = w45._rel_defect(
        energy_accum_norm_rate,
        expected_energy_norm_rate,
        volumetric_energy_norm_rate,
        primary_power / energy_scale,
        see_power / energy_scale,
    )

    expected_see_power = see_rate * ELEMENTARY_CHARGE_C * 4.0
    see_mapping_defect = w45._rel_defect(see_power, expected_see_power)

    ion_rates: dict[str, float] = {}
    for species, cfg in w45.combined.CHARGED.items():
        ion_rates[species] = (
            AVOGADRO
            * float(wall["charged"][species]["total_mass_rate_kg_s"])
            / float(cfg["molar_mass"])
        )
    positive_ion_charge_delta = -ELEMENTARY_CHARGE_C * (ion_rates["O2p"] + ion_rates["Op"]) * dt
    negative_ion_charge_delta = +ELEMENTARY_CHARGE_C * ion_rates["Om"] * dt
    primary_electron_charge_delta = +ELEMENTARY_CHARGE_C * primary_rate * dt
    see_electron_charge_delta = -ELEMENTARY_CHARGE_C * see_rate * dt
    expected_charge_delta = (
        positive_ion_charge_delta
        + negative_ion_charge_delta
        + primary_electron_charge_delta
        + see_electron_charge_delta
    )
    measured_charge_delta = (
        w45.s5r._num(final, "r31_charge_integral")
        - w45.s5r._num(initial, "r31_charge_integral")
    )
    charge_scale = max(
        abs(positive_ion_charge_delta)
        + abs(negative_ion_charge_delta)
        + abs(primary_electron_charge_delta)
        + abs(see_electron_charge_delta),
        1.0e-300,
    )
    charge_defect = abs(measured_charge_delta - expected_charge_delta) / charge_scale

    gauss = w45.s5r._gauss_evidence(case_dir / "input_out.csv")
    physical_rows = [row for row in rows if w45.s5r._num(row, "time") > 1.0e-15]
    state = w45.s5r._state_evidence(physical_rows)
    composition_error = max(
        abs(w45.s5r._num(final, "sum_w_min") - 1.0),
        abs(w45.s5r._num(final, "sum_w_max") - 1.0),
    )

    return {
        "dt_s": dt,
        "state": state,
        "gauss": gauss,
        "wall": wall,
        "electron_particle": {
            "units": "physical_particles_per_s",
            "accumulation_rate_s-1": electron_accumulation,
            "volumetric_source_rate_s-1": volumetric_electron_rate,
            "primary_wall_loss_rate_s-1": primary_rate,
            "see_wall_source_rate_s-1": see_rate,
            "expected_rate_s-1": expected_electron_rate,
            "relative_defect": electron_defect,
        },
        "electron_energy": {
            "representation": "frozen_normalized_T1",
            "accumulation_normalized_rate": energy_accum_norm_rate,
            "volumetric_source_normalized_rate": volumetric_energy_norm_rate,
            "primary_wall_power_W": primary_power,
            "see_wall_power_W": see_power,
            "expected_normalized_rate": expected_energy_norm_rate,
            "relative_defect": energy_defect,
        },
        "see_4eV_mapping": {
            "expected_power_W": expected_see_power,
            "measured_power_W": see_power,
            "relative_defect": see_mapping_defect,
        },
        "charge": {
            "ion_incident_particle_rate_s-1": ion_rates,
            "expected_delta_C": expected_charge_delta,
            "measured_delta_C": measured_charge_delta,
            "relative_defect_over_boundary_current_scale": charge_defect,
        },
        "composition_max_abs_error": composition_error,
        "n_e_min_m3": w45.s5r._num(final, "n_e_min"),
        "n_epsilon_min": w45.s5r._num(final, "s5r_n_epsilon_min"),
        "mean_energy_avg_eV": w45.s5r._num(final, "s5r_mean_en_avg"),
    }


def _evaluate(meta: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    gates = {
        "G01_t1_static_contract": t1.audit_t1_input(Path("issue243-case/input.i").read_text(encoding="utf-8"))["status"] == "PASS",
        "G02_stage5_state_invariants": metrics["state"].get("hard_pass") is True,
        "G03_wall_runtime_observables": metrics["wall"]["finite"] is True,
        "G04_electron_particle_balance": metrics["electron_particle"]["relative_defect"] <= w45.s5r.GENERIC_COUPLED_BALANCE_REL_TOL,
        "G05_electron_energy_balance": metrics["electron_energy"]["relative_defect"] <= w45.s5r.GENERIC_COUPLED_BALANCE_REL_TOL,
        "G06_four_ev_see_mapping": metrics["see_4eV_mapping"]["relative_defect"] <= w45.ALGEBRAIC_REL_TOL,
        "G07_boundary_current_charge_closure": metrics["charge"]["relative_defect_over_boundary_current_scale"] <= w45.RUNTIME_REL_TOL,
        "G08_gauss_closure": metrics["gauss"].get("status") == "MEASURED" and metrics["gauss"].get("relative_defect", math.inf) <= w45.s5r.MAX_GAUSS_RELATIVE_DEFECT,
        "G09_convergence_positivity": (
            metrics["n_e_min_m3"] >= 0.0
            and metrics["n_epsilon_min"] > 0.0
            and metrics["mean_energy_avg_eV"] > 0.0
            and metrics["composition_max_abs_error"] <= w45.COMPOSITION_ABS_TOL
        ),
        "G10_primary_energy_owner_active": metrics["electron_energy"]["primary_wall_power_W"] > 0.0,
    }
    return {"gates": gates, "scientific_hard_pass": all(gates.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, default=Path("issue243-case"))
    parser.add_argument("--input-file", type=Path, default=Path("issue243-case/input.i"))
    parser.add_argument("--summary", type=Path, default=Path("issue243-logs/p3-summary.json"))
    args = parser.parse_args()

    input_text = args.input_file.read_text(encoding="utf-8")
    _, meta = t1.build_t1_input()
    metrics = _metrics(args.case_dir, input_text, meta)
    decision = _evaluate(meta, metrics)
    summary = {
        "schema": "ISSUE243_T1_P3_V1",
        "claim": "coupled_one_step_log_molar_particle_with_frozen_energy_representation",
        "metrics": metrics,
        "decision": decision,
        "status": "PASS" if decision["scientific_hard_pass"] else "FAIL",
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.summary.read_text(encoding="utf-8"))
    return 0 if decision["scientific_hard_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
