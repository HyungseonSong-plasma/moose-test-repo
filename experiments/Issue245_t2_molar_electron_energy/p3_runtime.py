#!/usr/bin/env python3
"""Issue #245 T2 P3 coupled one-step molar-energy qualification."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from experiments.Issue217_sheath_energy_closure import run as w45
from experiments.Issue27_surface_reactions.controlled_wall import see as a8
from experiments.historical_recipe_support import issue26_energy_chain as energy
from experiments.Issue245_t2_molar_electron_energy import run as t2

ELEMENTARY_CHARGE_C = 1.602176634e-19
AVOGADRO = 6.02214076e23
ENERGY_MOLAR_TO_J = AVOGADRO * ELEMENTARY_CHARGE_C

# Exact-head Issue-243 P3 reference from workflow run 35191840043 at
# 8be91303bfe408d02fc200d7295062e936e8c4b9. These are physical observables,
# not normalized coordinates.
T1_REFERENCE = {
    "n_e_min_m3": 1.2940803272683e18,
    "n_e_avg_m3": 1.2979143380597e18,
    "mean_energy_avg_eV": 5.732345937393,
    "phi_min_V": 10.896063852554,
    "phi_max_V": 18.55025394824,
    "energy_inventory_J": 0.05973016115932386,
    "primary_wall_power_W": 26726.675072372,
    "see_wall_power_W": 155.05511874288,
    "charge_delta_C": 4.8957270170967e-08,
}


def _relative(value: float, reference: float) -> float:
    return abs(value - reference) / max(abs(reference), 1.0e-300)


def _metrics(case_dir: Path, input_text: str) -> dict[str, Any]:
    rows = w45.s5r._read_rows(case_dir / "input_out.csv")
    if len(rows) < 2:
        raise RuntimeError("P3 requires INITIAL and TIMESTEP_END rows")
    initial, final = rows[0], rows[-1]
    dt = w45.s5r._num(final, "time") - w45.s5r._num(initial, "time")
    if dt <= 0.0:
        raise RuntimeError(f"non-positive P3 dt={dt}")

    volume = w45.s5r._num(final, "domain_volume")
    wall = w45._wall_observables(final)

    # Particle subsystem remains the accepted T1 molar representation.
    primary_particle_molar = w45._physical(w45.s5r._num(final, w45.PARTICLE_PP))
    see_particle_molar = w45._physical(w45.s5r._num(final, a8.SEE_PP))
    primary_particle_rate = AVOGADRO * primary_particle_molar
    see_particle_rate = AVOGADRO * see_particle_molar
    electron_accumulation = (
        w45.s5r._num(final, "n_e_inventory")
        - w45.s5r._num(initial, "n_e_inventory")
    ) / dt
    volumetric_electron_rate = w45.s5r._num(final, "s5r_electron_source_avg") * volume
    expected_electron_rate = volumetric_electron_rate + see_particle_rate - primary_particle_rate
    electron_defect = w45._rel_defect(
        electron_accumulation,
        expected_electron_rate,
        volumetric_electron_rate,
        see_particle_rate,
        primary_particle_rate,
    )

    # T2 electron-energy ledger is conservative eV*mol rather than a normalized
    # coordinate. The inherited source evaluator now returns eV mol/(m^3 s).
    coefficients = w45.s5r._energy_coefficients(input_text)
    volumetric_energy_molar_rate = w45.s5r._energy_source_density(final, coefficients) * volume
    energy_accum_molar_rate = (
        w45.s5r._num(final, "s5r_n_epsilon_inventory")
        - w45.s5r._num(initial, "s5r_n_epsilon_inventory")
    ) / dt
    primary_energy_molar_rate = w45._physical(
        w45.s5r._num(final, w45.ENERGY_RATE_PP)
    )
    see_energy_molar_rate = w45._physical(
        w45.s5r._num(final, energy.SEE_ENERGY_RATE_PP)
    )
    expected_energy_molar_rate = (
        volumetric_energy_molar_rate
        - primary_energy_molar_rate
        + see_energy_molar_rate
    )
    energy_molar_defect = w45._rel_defect(
        energy_accum_molar_rate,
        expected_energy_molar_rate,
        volumetric_energy_molar_rate,
        primary_energy_molar_rate,
        see_energy_molar_rate,
    )

    # Independent SI ledger using the explicit J inventory and W wall outputs.
    energy_accum_W = (
        w45.s5r._num(final, t2.ENERGY_INVENTORY_J)
        - w45.s5r._num(initial, t2.ENERGY_INVENTORY_J)
    ) / dt
    volumetric_energy_W = volumetric_energy_molar_rate * ENERGY_MOLAR_TO_J
    primary_power = w45._physical(w45.s5r._num(final, w45.ENERGY_POWER_PP))
    see_power = w45._physical(
        w45.s5r._num(final, energy.SEE_ENERGY_COUPLED_POWER_PP)
    )
    expected_energy_W = volumetric_energy_W - primary_power + see_power
    energy_si_defect = w45._rel_defect(
        energy_accum_W,
        expected_energy_W,
        volumetric_energy_W,
        primary_power,
        see_power,
    )

    scaling_checks = {
        "accumulation": w45._rel_defect(
            energy_accum_W, energy_accum_molar_rate * ENERGY_MOLAR_TO_J
        ),
        "primary_wall": w45._rel_defect(
            primary_power, primary_energy_molar_rate * ENERGY_MOLAR_TO_J
        ),
        "see_wall": w45._rel_defect(
            see_power, see_energy_molar_rate * ENERGY_MOLAR_TO_J
        ),
    }

    expected_see_energy_molar_rate = 4.0 * see_particle_molar
    see_molar_mapping_defect = w45._rel_defect(
        see_energy_molar_rate, expected_see_energy_molar_rate
    )
    expected_see_power = see_particle_rate * ELEMENTARY_CHARGE_C * 4.0
    see_power_mapping_defect = w45._rel_defect(see_power, expected_see_power)

    ion_rates: dict[str, float] = {}
    for species, cfg in w45.combined.CHARGED.items():
        ion_rates[species] = (
            AVOGADRO
            * float(wall["charged"][species]["total_mass_rate_kg_s"])
            / float(cfg["molar_mass"])
        )
    positive_ion_charge_delta = -ELEMENTARY_CHARGE_C * (
        ion_rates["O2p"] + ion_rates["Op"]
    ) * dt
    negative_ion_charge_delta = +ELEMENTARY_CHARGE_C * ion_rates["Om"] * dt
    primary_electron_charge_delta = +ELEMENTARY_CHARGE_C * primary_particle_rate * dt
    see_electron_charge_delta = -ELEMENTARY_CHARGE_C * see_particle_rate * dt
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

    physical = {
        "n_e_min_m3": w45.s5r._num(final, "n_e_min"),
        "n_e_avg_m3": w45.s5r._num(final, "n_e_avg"),
        "mean_energy_avg_eV": w45.s5r._num(final, "s5r_mean_en_avg"),
        "phi_min_V": w45.s5r._num(final, w45.PHI_MIN_PP),
        "phi_max_V": w45.s5r._num(final, w45.PHI_MAX_PP),
        "energy_inventory_J": w45.s5r._num(final, t2.ENERGY_INVENTORY_J),
        "primary_wall_power_W": primary_power,
        "see_wall_power_W": see_power,
        "charge_delta_C": measured_charge_delta,
    }
    equivalence = {
        key: {
            "value": value,
            "reference": T1_REFERENCE[key],
            "relative_difference": _relative(value, T1_REFERENCE[key]),
        }
        for key, value in physical.items()
    }
    state_keys = (
        "n_e_min_m3",
        "n_e_avg_m3",
        "mean_energy_avg_eV",
        "phi_min_V",
        "phi_max_V",
    )
    integral_keys = (
        "energy_inventory_J",
        "primary_wall_power_W",
        "see_wall_power_W",
        "charge_delta_C",
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
            "primary_wall_loss_rate_s-1": primary_particle_rate,
            "see_wall_source_rate_s-1": see_particle_rate,
            "relative_defect": electron_defect,
        },
        "electron_energy_molar": {
            "units": "eV_mol_per_s",
            "accumulation_rate": energy_accum_molar_rate,
            "volumetric_source_rate": volumetric_energy_molar_rate,
            "primary_wall_loss_rate": primary_energy_molar_rate,
            "see_wall_source_rate": see_energy_molar_rate,
            "expected_rate": expected_energy_molar_rate,
            "relative_defect": energy_molar_defect,
        },
        "electron_energy_si": {
            "units": "W",
            "accumulation_W": energy_accum_W,
            "volumetric_source_W": volumetric_energy_W,
            "primary_wall_power_W": primary_power,
            "see_wall_power_W": see_power,
            "expected_W": expected_energy_W,
            "relative_defect": energy_si_defect,
        },
        "molar_to_si_scaling": {
            "factor_J_per_eV_mol": ENERGY_MOLAR_TO_J,
            "relative_defects": scaling_checks,
        },
        "see_4eV_mapping": {
            "expected_energy_molar_rate": expected_see_energy_molar_rate,
            "measured_energy_molar_rate": see_energy_molar_rate,
            "molar_relative_defect": see_molar_mapping_defect,
            "expected_power_W": expected_see_power,
            "measured_power_W": see_power,
            "power_relative_defect": see_power_mapping_defect,
        },
        "charge": {
            "ion_incident_particle_rate_s-1": ion_rates,
            "expected_delta_C": expected_charge_delta,
            "measured_delta_C": measured_charge_delta,
            "relative_defect_over_boundary_current_scale": charge_defect,
        },
        "composition_max_abs_error": composition_error,
        "c_epsilon_min_eV_mol_m3": w45.s5r._num(final, t2.C_EPSILON_MIN),
        "mean_energy_avg_eV": physical["mean_energy_avg_eV"],
        "physical_observables": physical,
        "t1_reference_equivalence": {
            "reference_head": "8be91303bfe408d02fc200d7295062e936e8c4b9",
            "reference_workflow_run": 35191840043,
            "observables": equivalence,
            "state_max_relative_difference": max(
                equivalence[key]["relative_difference"] for key in state_keys
            ),
            "integral_max_relative_difference": max(
                equivalence[key]["relative_difference"] for key in integral_keys
            ),
        },
    }


def _evaluate(metrics: dict[str, Any], input_text: str) -> dict[str, Any]:
    scaling_max = max(metrics["molar_to_si_scaling"]["relative_defects"].values())
    equivalence = metrics["t1_reference_equivalence"]
    gates = {
        "G01_t2_static_contract": t2.audit_t2_input(input_text)["status"] == "PASS",
        "G02_stage5_state_invariants": metrics["state"].get("hard_pass") is True,
        "G03_wall_runtime_observables": metrics["wall"]["finite"] is True,
        "G04_electron_particle_balance": metrics["electron_particle"]["relative_defect"]
        <= w45.s5r.GENERIC_COUPLED_BALANCE_REL_TOL,
        "G05_electron_energy_molar_balance": metrics["electron_energy_molar"]["relative_defect"]
        <= w45.s5r.GENERIC_COUPLED_BALANCE_REL_TOL,
        "G06_electron_energy_si_balance": metrics["electron_energy_si"]["relative_defect"]
        <= w45.s5r.GENERIC_COUPLED_BALANCE_REL_TOL,
        "G07_molar_to_si_exact_scaling": scaling_max <= w45.ALGEBRAIC_REL_TOL,
        "G08_four_ev_see_mapping": max(
            metrics["see_4eV_mapping"]["molar_relative_defect"],
            metrics["see_4eV_mapping"]["power_relative_defect"],
        ) <= w45.ALGEBRAIC_REL_TOL,
        "G09_boundary_current_charge_closure": metrics["charge"]["relative_defect_over_boundary_current_scale"]
        <= w45.RUNTIME_REL_TOL,
        "G10_gauss_closure": metrics["gauss"].get("status") == "MEASURED"
        and metrics["gauss"].get("relative_defect", math.inf)
        <= w45.s5r.MAX_GAUSS_RELATIVE_DEFECT,
        "G11_convergence_positivity": metrics["c_epsilon_min_eV_mol_m3"] > 0.0
        and metrics["mean_energy_avg_eV"] > 0.0
        and metrics["composition_max_abs_error"] <= w45.COMPOSITION_ABS_TOL,
        "G12_t1_physical_equivalence": equivalence["state_max_relative_difference"] <= 1.0e-2
        and equivalence["integral_max_relative_difference"] <= 1.0e-3,
    }
    return {"gates": gates, "scientific_hard_pass": all(gates.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, default=Path("issue245-case"))
    parser.add_argument("--input-file", type=Path, default=Path("issue245-case/input.i"))
    parser.add_argument("--summary", type=Path, default=Path("issue245-logs/p3-summary.json"))
    args = parser.parse_args()

    input_text = args.input_file.read_text(encoding="utf-8")
    metrics = _metrics(args.case_dir, input_text)
    decision = _evaluate(metrics, input_text)
    summary = {
        "schema": "ISSUE245_T2_P3_V1",
        "claim": "coupled_one_step_log_molar_particle_plus_conservative_molar_energy",
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
