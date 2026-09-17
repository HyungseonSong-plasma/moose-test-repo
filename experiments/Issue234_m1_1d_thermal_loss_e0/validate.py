#!/usr/bin/env python3
"""Validate Issue #234 1D E=0 electron diffusion + thermal surface-loss discriminator."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input.i"
CSV = ROOT / "input_out.csv"

AVOGADRO = 6.02214076e23
ELEMENTARY_CHARGE_C = 1.602176634e-19
ELECTRON_MASS_KG = 9.1093837139e-31
N0_M3 = 1.0e18
MEAN_EN_EV = 5.73276
D_E_M2_S = 41257.29899041419
L_M = 0.01
NX = 10
DT_S = 1.0e-10
N_STEPS = 10


def thermal_speed_m_s(mean_energy_eV: float) -> float:
    return math.sqrt(
        16.0 * ELEMENTARY_CHARGE_C * mean_energy_eV
        / (3.0 * math.pi * ELECTRON_MASS_KG)
    )


def static_contract() -> dict[str, bool]:
    text = INPUT.read_text(encoding="utf-8")
    checks = {
        "one_dimensional": "dim = 1" in text,
        "exact_initial_log_state": "initial_condition = -13.30836826905085" in text,
        "log_molar_time": "type = PhysicsFVLogMolarElectronTimeDerivative" in text,
        "production_log_diffusion": "type = PhysicsFVLogMolarElectronDiffusion" in text,
        "constant_diffusion_exact": "41257.29899041419" in text,
        "zero_prescribed_field": "expression = '0.0*x'" in text,
        "production_log_drift_object_present": "type = PhysicsFVLogMolarElectrostaticDrift" in text,
        "electron_charge_minus_one": "charge_number = -1" in text,
        "pure_thermal_quarter_flux": "0.25*exp(loge)*sqrt(" in text,
        "thermal_wall_factor_outward": "factor = -1" in text,
        "no_sheath_bc": "PhysicsFVElectronGroundedSheathCollectionBC" not in text,
        "no_poisson_solve": "potential_plasma" not in text and "PhysicsFVPoisson" not in text,
        "no_reaction_source": "ReactionSource" not in text,
        "no_energy_solve": "c_epsilon" not in text and "n_epsilon" not in text,
        "no_secondary_emission_object": "secondary_emission" not in text.lower() and "see_bc" not in text.lower(),
        "automatic_scaling_off": "automatic_scaling = false" in text,
        "right_wall_only": "boundary = right" in text,
        "exodus_enabled": "exodus = true" in text,
    }
    return checks


def main() -> int:
    checks = static_contract()
    failed_static = sorted(name for name, ok in checks.items() if not ok)
    if failed_static:
        raise SystemExit(f"static contract failed: {failed_static}")

    rows = list(csv.DictReader(CSV.open(newline="", encoding="utf-8")))
    if len(rows) != N_STEPS + 1:
        raise SystemExit(f"expected {N_STEPS + 1} CSV rows including INITIAL, got {len(rows)}")

    initial = rows[0]
    final = rows[-1]
    required = (
        "time",
        "c_e_inventory_per_area",
        "n_e_min",
        "n_e_max",
        "wall_thermal_flux_rate_per_area",
        "wall_thermal_loss_integral_per_area",
    )
    missing = [name for name in required if name not in final]
    if missing:
        raise SystemExit(f"missing CSV columns: {missing}")

    vals0 = {name: float(initial[name]) for name in required}
    valsf = {name: float(final[name]) for name in required}
    if not all(math.isfinite(value) for value in (*vals0.values(), *valsf.values())):
        raise SystemExit("non-finite CSV value")

    c0 = N0_M3 / AVOGADRO
    inventory_initial_expected = c0 * L_M
    vbar = thermal_speed_m_s(MEAN_EN_EV)
    k_wall = 0.25 * vbar
    diffusion_length = math.sqrt(2.0 * D_E_M2_S * N_STEPS * DT_S)

    def close(a: float, b: float, rel: float = 2.0e-8, abs_: float = 1.0e-16) -> bool:
        return math.isclose(a, b, rel_tol=rel, abs_tol=abs_)

    inventory_loss = vals0["c_e_inventory_per_area"] - valsf["c_e_inventory_per_area"]
    spread = valsf["n_e_max"] - valsf["n_e_min"]
    relative_spread = spread / valsf["n_e_max"] if valsf["n_e_max"] > 0.0 else math.inf

    runtime_checks = {
        "final_time": close(valsf["time"], N_STEPS * DT_S, rel=0.0, abs_=1.0e-18),
        "initial_inventory": close(vals0["c_e_inventory_per_area"], inventory_initial_expected),
        "inventory_decreases": valsf["c_e_inventory_per_area"] < vals0["c_e_inventory_per_area"],
        "density_positive": valsf["n_e_min"] > 0.0,
        "ordered_extrema": 0.0 < valsf["n_e_min"] < valsf["n_e_max"] < N0_M3,
        "bulk_responds_to_diffusion": valsf["n_e_max"] < 0.999999 * N0_M3,
        "wall_gradient_present": relative_spread > 1.0e-6,
        "integrated_wall_loss_positive": valsf["wall_thermal_loss_integral_per_area"] > 0.0,
        "final_wall_flux_positive": valsf["wall_thermal_flux_rate_per_area"] > 0.0,
        "particle_ledger": close(
            inventory_loss,
            valsf["wall_thermal_loss_integral_per_area"],
            rel=2.0e-8,
            abs_=1.0e-16,
        ),
    }
    failed_runtime = sorted(name for name, ok in runtime_checks.items() if not ok)

    summary = {
        "status": "PASS" if not failed_runtime else "FAIL",
        "claim_scope": "1D E=0 constant electron diffusion plus pure thermal right-wall loss",
        "static_checks": checks,
        "runtime_checks": runtime_checks,
        "constants": {
            "n0_m3": N0_M3,
            "c0_mol_m3": c0,
            "mean_energy_eV": MEAN_EN_EV,
            "electron_diffusion_m2_s": D_E_M2_S,
            "thermal_mean_speed_m_s": vbar,
            "thermal_wall_speed_coefficient_m_s": k_wall,
            "length_m": L_M,
            "nx": NX,
            "dx_m": L_M / NX,
            "dt_s": DT_S,
            "n_steps": N_STEPS,
            "electric_field_V_m": 0.0,
            "diffusion_length_over_run_m": diffusion_length,
        },
        "measured": {
            **valsf,
            "inventory_loss_mol_m2": inventory_loss,
            "density_relative_spread": relative_spread,
        },
        "failed_runtime_checks": failed_runtime,
        "science_claim": False,
        "timestep_convergence_claim": False,
    }
    (ROOT / "validation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if failed_runtime:
        raise SystemExit(f"runtime validation failed: {failed_runtime}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
