#!/usr/bin/env python3
"""Validate Issue #234 electron-only one-way Poisson observer."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_ROOT = ROOT.parent / "Issue234_m1_1d_electron_drift_surface"
CONTROL_CSV = BASE_ROOT / "input_drift_surface_out.csv"
CANDIDATE_CSV = ROOT / "input_poisson_observer_out.csv"
INPUT = ROOT / "input_poisson_observer.i"

END_S = 5.0e-10


def read_rows(path: Path, required: tuple[str, ...]) -> list[dict[str, float]]:
    rows_raw = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if len(rows_raw) != 11:
        raise SystemExit(f"{path.name}: expected 11 rows including INITIAL, got {len(rows_raw)}")
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


def rel_diff(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1.0e-30)


def main() -> int:
    text = INPUT.read_text(encoding="utf-8")
    static = {
        "observer_state_present": "[potential_plasma]" in text,
        "electron_transport_still_prescribed": "potential = phi_ramp" in text,
        "poisson_feedback_off": "potential = potential_plasma" not in text,
        "fixed_positive_background": "1.602176634e-19*(1.0e18-ne)" in text,
        "poisson_operator_present": "[phi_diffusion]" in text and "[phi_charge_source]" in text,
        "left_ground": "[left_ground]" in text and "boundary = left" in text,
        "gauss_observables": "[charge_integral]" in text and "[gauss_flux_charge]" in text,
        "no_heavy_evolution": "PhysicsFVConservativeMassFractionTimeDerivative" not in text
        and "INSFVMassAdvection" not in text,
        "no_energy_solve": "c_epsilon" not in text and "n_epsilon" not in text,
        "no_chemistry": "ReactionSource" not in text,
        "no_diffusion": "PhysicsFVLogMolarElectronDiffusion" not in text,
        "automatic_scaling_off": "automatic_scaling = false" in text,
    }
    failed_static = sorted(k for k, ok in static.items() if not ok)
    if failed_static:
        raise SystemExit(f"static contract failed: {failed_static}")

    particle_cols = (
        "time",
        "c_e_inventory_per_area",
        "c_e_x_moment_per_area",
        "n_e_min",
        "n_e_max",
        "wall_thermal_flux_rate_per_area",
        "wall_thermal_loss_integral_per_area",
    )
    candidate_cols = particle_cols + (
        "charge_integral",
        "phi_min",
        "phi_max",
        "gauss_flux_charge",
    )

    control = read_rows(CONTROL_CSV, particle_cols)
    candidate = read_rows(CANDIDATE_CSV, candidate_cols)
    c0, cf = control[0], control[-1]
    p0, pf = candidate[0], candidate[-1]

    control_inventory_loss = c0["c_e_inventory_per_area"] - cf["c_e_inventory_per_area"]
    candidate_inventory_loss = p0["c_e_inventory_per_area"] - pf["c_e_inventory_per_area"]
    candidate_wall_loss = pf["wall_thermal_loss_integral_per_area"]
    particle_ledger_rel = abs(candidate_inventory_loss - candidate_wall_loss) / max(
        abs(candidate_inventory_loss), abs(candidate_wall_loss), 1.0e-30
    )

    particle_parity = {
        key: rel_diff(pf[key], cf[key])
        for key in (
            "c_e_inventory_per_area",
            "c_e_x_moment_per_area",
            "n_e_min",
            "n_e_max",
            "wall_thermal_flux_rate_per_area",
            "wall_thermal_loss_integral_per_area",
        )
    }

    q0 = p0["charge_integral"]
    qv = pf["charge_integral"]
    qf = pf["gauss_flux_charge"]
    gauss_abs = qf - qv
    gauss_rel = abs(gauss_abs) / max(abs(qf), abs(qv), 1.0e-30)
    phi_span = pf["phi_max"] - pf["phi_min"]

    runtime = {
        "final_time": math.isclose(pf["time"], END_S, rel_tol=0.0, abs_tol=1.0e-18),
        "initial_quasi_neutral": abs(q0) < 1.0e-12,
        "particle_density_positive": pf["n_e_min"] > 0.0,
        "particle_inventory_decreases": 0.0
        < pf["c_e_inventory_per_area"]
        < p0["c_e_inventory_per_area"],
        "particle_wall_ledger": particle_ledger_rel < 2.0e-7,
        "observer_does_not_change_particle_solution": max(particle_parity.values()) < 5.0e-8,
        "final_charge_nonzero": abs(qv) > 1.0e-10,
        "poisson_potential_finite": math.isfinite(pf["phi_min"]) and math.isfinite(pf["phi_max"]),
        "poisson_potential_nontrivial": abs(phi_span) > 1.0e-6,
        "gauss_flux_nonzero": abs(qf) > 1.0e-10,
        "gauss_orientation_consistent": qv * qf > 0.0,
        "gauss_closure": gauss_rel < 1.0e-6,
    }
    failed = sorted(k for k, ok in runtime.items() if not ok)

    summary = {
        "status": "PASS" if not failed else "FAIL",
        "claim_scope": (
            "electron-only one-way Poisson observation on the accepted prescribed-field "
            "drift + right-wall-loss baseline"
        ),
        "static_checks": static,
        "runtime_checks": runtime,
        "particle_control_parity_relative": particle_parity,
        "control_particle_ledger": {
            "inventory_loss_mol_per_m2": control_inventory_loss,
            "integrated_wall_loss_mol_per_m2": cf["wall_thermal_loss_integral_per_area"],
        },
        "candidate_particle_ledger": {
            "inventory_loss_mol_per_m2": candidate_inventory_loss,
            "integrated_wall_loss_mol_per_m2": candidate_wall_loss,
            "relative_defect": particle_ledger_rel,
        },
        "poisson_observer": {
            "initial_charge_integral_C_per_m2": q0,
            "final_charge_integral_C_per_m2": qv,
            "final_gauss_flux_C_per_m2": qf,
            "gauss_absolute_defect_C_per_m2": gauss_abs,
            "gauss_relative_defect": gauss_rel,
            "phi_min_V": pf["phi_min"],
            "phi_max_V": pf["phi_max"],
            "phi_span_V": phi_span,
        },
        "failed_runtime_checks": failed,
        "science_claim": False,
        "closed_electron_poisson_feedback_claim": False,
        "m1_acceptance_claim": False,
    }
    (ROOT / "validation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(f"runtime validation failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
