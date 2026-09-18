#!/usr/bin/env python3
"""Validate Issue #234 1D prescribed-field electron drift and drift+surface-loss discriminators."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DRIFT_INPUT = ROOT / "input_drift_only.i"
SURFACE_INPUT = ROOT / "input_drift_surface.i"
CONTROL_INPUT = ROOT / "input_sign_control.i"

DRIFT_CSV = ROOT / "input_drift_only_out.csv"
SURFACE_CSV = ROOT / "input_drift_surface_out.csv"
CONTROL_CSV = ROOT / "input_sign_control_out.csv"

AVOGADRO = 6.02214076e23
N0_M3 = 1.0e18
L_M = 0.01
NX = 20
DX_M = L_M / NX
MU_E = 9755.114369721427
DPHI_DX = 100.0
E_X = -DPHI_DX
ELECTRON_Z = -1.0
DT_S = 5.0e-11
N_STEPS = 10
END_S = DT_S * N_STEPS
EXPECTED_ELECTRON_DRIFT_V = ELECTRON_Z * MU_E * E_X
EXPECTED_DISPLACEMENT_M = EXPECTED_ELECTRON_DRIFT_V * END_S


def prepare_sign_control() -> Path:
    text = DRIFT_INPUT.read_text(encoding="utf-8")
    needle = "charge_number = -1"
    if text.count(needle) != 1:
        raise RuntimeError(f"expected exactly one electron charge-number anchor, got {text.count(needle)}")
    control = text.replace(needle, "charge_number = 1", 1)
    CONTROL_INPUT.write_text(control, encoding="utf-8")
    return CONTROL_INPUT


def static_contract() -> dict[str, bool]:
    drift = DRIFT_INPUT.read_text(encoding="utf-8")
    surface = SURFACE_INPUT.read_text(encoding="utf-8")
    prepare_sign_control()
    control = CONTROL_INPUT.read_text(encoding="utf-8")

    common = drift + "\n" + surface
    checks = {
        "one_dimensional_both": drift.count("dim = 1") == 1 and surface.count("dim = 1") == 1,
        "production_log_time_both": drift.count("type = PhysicsFVLogMolarElectronTimeDerivative") == 1
        and surface.count("type = PhysicsFVLogMolarElectronTimeDerivative") == 1,
        "production_log_drift_both": drift.count("type = PhysicsFVLogMolarElectrostaticDrift") == 1
        and surface.count("type = PhysicsFVLogMolarElectrostaticDrift") == 1,
        "prescribed_linear_potential_both": drift.count("expression = '100.0*x'") == 1
        and surface.count("expression = '100.0*x'") == 1,
        "electron_charge_minus_one_both": drift.count("charge_number = -1") == 1
        and surface.count("charge_number = -1") == 1,
        "interior_drift_boundary_ownership_both": drift.count("boundaries_to_avoid = 'left right'") == 1
        and surface.count("boundaries_to_avoid = 'left right'") == 1,
        "no_diffusion_both": "PhysicsFVLogMolarElectronDiffusion" not in common,
        "no_poisson_both": "potential_plasma" not in common and "PhysicsFVPoisson" not in common,
        "no_reaction_source_both": "ReactionSource" not in common,
        "no_energy_solve_both": "c_epsilon" not in common and "n_epsilon" not in common,
        "no_see_both": "secondary_emission" not in common.lower() and "see_bc" not in common.lower(),
        "automatic_scaling_off_both": drift.count("automatic_scaling = false") == 1
        and surface.count("automatic_scaling = false") == 1,
        "same_fixed_dt_both": drift.count("dt = 5.0e-11") == 1 and surface.count("dt = 5.0e-11") == 1,
        "same_end_time_both": drift.count("end_time = 5.0e-10") == 1
        and surface.count("end_time = 5.0e-10") == 1,
        "centroid_observable_both": drift.count("c_e_x_moment_per_area") >= 1
        and surface.count("c_e_x_moment_per_area") >= 1,
        "drift_only_has_no_wall_bc": "right_thermal_surface_loss" not in drift,
        "surface_has_single_wall_bc": surface.count("[right_thermal_surface_loss]") == 1
        and surface.count("functor = thermal_flux_molar_outward") >= 1
        and surface.count("factor = -1") == 1,
        "surface_has_integrated_wall_loss": surface.count("[wall_thermal_loss_integral_per_area]") == 1,
        "sign_control_only_flips_charge": control
        == drift.replace("charge_number = -1", "charge_number = 1", 1),
        "sign_control_positive_charge": control.count("charge_number = 1") == 1
        and "charge_number = -1" not in control,
        "exodus_all_base_cases": drift.count("exodus = true") == 1 and surface.count("exodus = true") == 1,
    }
    return checks


def read_rows(path: Path, required: tuple[str, ...]) -> list[dict[str, float]]:
    rows_raw = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if len(rows_raw) != N_STEPS + 1:
        raise SystemExit(f"{path.name}: expected {N_STEPS + 1} rows including INITIAL, got {len(rows_raw)}")
    missing = [name for name in required if name not in rows_raw[-1]]
    if missing:
        raise SystemExit(f"{path.name}: missing columns {missing}")
    rows: list[dict[str, float]] = []
    for row in rows_raw:
        vals = {name: float(row[name]) for name in required}
        if not all(math.isfinite(v) for v in vals.values()):
            raise SystemExit(f"{path.name}: non-finite value")
        rows.append(vals)
    return rows


def close(a: float, b: float, rel: float = 2.0e-8, abs_: float = 1.0e-16) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_)


def centroid(row: dict[str, float]) -> float:
    return row["c_e_x_moment_per_area"] / row["c_e_inventory_per_area"]


def inventory_rel_defect(initial: dict[str, float], final: dict[str, float]) -> float:
    return abs(final["c_e_inventory_per_area"] - initial["c_e_inventory_per_area"]) / max(
        abs(initial["c_e_inventory_per_area"]), 1.0e-30
    )


def main() -> int:
    checks = static_contract()
    failed_static = sorted(name for name, ok in checks.items() if not ok)
    if failed_static:
        raise SystemExit(f"static contract failed: {failed_static}")

    base_required = (
        "time",
        "c_e_inventory_per_area",
        "c_e_x_moment_per_area",
        "n_e_min",
        "n_e_max",
    )
    surface_required = base_required + (
        "wall_thermal_flux_rate_per_area",
        "wall_thermal_loss_integral_per_area",
    )

    drift_rows = read_rows(DRIFT_CSV, base_required)
    control_rows = read_rows(CONTROL_CSV, base_required)
    surface_rows = read_rows(SURFACE_CSV, surface_required)

    d0, df = drift_rows[0], drift_rows[-1]
    c0, cf = control_rows[0], control_rows[-1]
    s0, sf = surface_rows[0], surface_rows[-1]

    c_initial_expected = N0_M3 / AVOGADRO
    inventory_initial_expected = c_initial_expected * L_M
    centroid_initial_expected = 0.5 * L_M

    drift_shift = centroid(df) - centroid(d0)
    control_shift = centroid(cf) - centroid(c0)
    drift_inventory_defect = inventory_rel_defect(d0, df)
    control_inventory_defect = inventory_rel_defect(c0, cf)

    surface_inventory_loss = s0["c_e_inventory_per_area"] - sf["c_e_inventory_per_area"]
    wall_loss = sf["wall_thermal_loss_integral_per_area"]
    surface_ledger_rel = abs(surface_inventory_loss - wall_loss) / max(
        abs(surface_inventory_loss), abs(wall_loss), 1.0e-30
    )

    drift_runtime = {
        "final_time": close(df["time"], END_S, rel=0.0, abs_=1.0e-18),
        "initial_inventory": close(d0["c_e_inventory_per_area"], inventory_initial_expected),
        "initial_centroid": close(centroid(d0), centroid_initial_expected, rel=0.0, abs_=1.0e-12),
        "inventory_conserved": drift_inventory_defect < 2.0e-8,
        "density_positive": df["n_e_min"] > 0.0,
        "redistribution_present": df["n_e_min"] < 0.9999 * N0_M3
        and df["n_e_max"] > 1.0001 * N0_M3,
        "electron_drift_moves_plus_x": drift_shift > 1.0e-5,
    }

    control_runtime = {
        "final_time": close(cf["time"], END_S, rel=0.0, abs_=1.0e-18),
        "inventory_conserved": control_inventory_defect < 2.0e-8,
        "density_positive": cf["n_e_min"] > 0.0,
        "positive_charge_control_moves_minus_x": control_shift < -1.0e-5,
        "opposite_sign_response": drift_shift * control_shift < 0.0,
        "comparable_shift_magnitude": 0.8
        < abs(drift_shift) / max(abs(control_shift), 1.0e-30)
        < 1.25,
    }

    surface_runtime = {
        "final_time": close(sf["time"], END_S, rel=0.0, abs_=1.0e-18),
        "initial_inventory": close(s0["c_e_inventory_per_area"], inventory_initial_expected),
        "density_positive": sf["n_e_min"] > 0.0,
        "inventory_decreases": 0.0
        < sf["c_e_inventory_per_area"]
        < s0["c_e_inventory_per_area"],
        "wall_flux_positive": sf["wall_thermal_flux_rate_per_area"] > 0.0,
        "wall_loss_integral_positive": wall_loss > 0.0,
        "particle_ledger": surface_ledger_rel < 2.0e-7,
        "wall_case_loses_more_inventory_than_closed_drift_case": sf["c_e_inventory_per_area"]
        < df["c_e_inventory_per_area"],
    }

    failed_runtime = {
        "drift_only": sorted(k for k, ok in drift_runtime.items() if not ok),
        "sign_control": sorted(k for k, ok in control_runtime.items() if not ok),
        "drift_surface": sorted(k for k, ok in surface_runtime.items() if not ok),
    }
    hard_fail = any(failed_runtime.values())

    summary = {
        "status": "PASS" if not hard_fail else "FAIL",
        "claim_scope": (
            "1D prescribed-field log-molar electron drift direction/conservation plus "
            "independently owned right-wall thermal collection"
        ),
        "static_checks": checks,
        "numerical_contract": {
            "length_m": L_M,
            "nx": NX,
            "dx_m": DX_M,
            "dt_s": DT_S,
            "steps": N_STEPS,
            "end_time_s": END_S,
            "dphi_dx_V_per_m": DPHI_DX,
            "electric_field_x_V_per_m": E_X,
            "electron_charge_number": ELECTRON_Z,
            "mobility_m2_per_V_s": MU_E,
            "expected_electron_drift_velocity_m_per_s": EXPECTED_ELECTRON_DRIFT_V,
            "expected_free_drift_displacement_m": EXPECTED_DISPLACEMENT_M,
            "single_step_drift_CFL": abs(EXPECTED_ELECTRON_DRIFT_V) * DT_S / DX_M,
        },
        "drift_only": {
            "checks": drift_runtime,
            "initial_centroid_m": centroid(d0),
            "final_centroid_m": centroid(df),
            "centroid_shift_m": drift_shift,
            "inventory_relative_defect": drift_inventory_defect,
            "final_n_e_min_m3": df["n_e_min"],
            "final_n_e_max_m3": df["n_e_max"],
        },
        "positive_charge_mutation_control": {
            "checks": control_runtime,
            "initial_centroid_m": centroid(c0),
            "final_centroid_m": centroid(cf),
            "centroid_shift_m": control_shift,
            "inventory_relative_defect": control_inventory_defect,
            "final_n_min_m3": cf["n_e_min"],
            "final_n_max_m3": cf["n_e_max"],
        },
        "drift_plus_surface_loss": {
            "checks": surface_runtime,
            "initial_centroid_m": centroid(s0),
            "final_centroid_m": centroid(sf),
            "inventory_loss_mol_per_m2": surface_inventory_loss,
            "integrated_wall_loss_mol_per_m2": wall_loss,
            "ledger_relative_defect": surface_ledger_rel,
            "final_n_e_min_m3": sf["n_e_min"],
            "final_n_e_max_m3": sf["n_e_max"],
        },
        "failed_runtime_checks": failed_runtime,
        "science_claim": False,
        "timestep_convergence_claim": False,
        "m1_acceptance_claim": False,
    }
    (ROOT / "validation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if hard_fail:
        raise SystemExit(f"runtime validation failed: {failed_runtime}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
