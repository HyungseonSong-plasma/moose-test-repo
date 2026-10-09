#!/usr/bin/env python3
"""Integrated acceptance checks for Issue #3 D6 2D dielectric coupling."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

E = 1.602176634e-19
EPS0 = 8.8541878128e-12
GAMMA = 0.05
DT = 1.0e-9
NSTEPS = 5
PLASMA_VOLUME_2D = 2.0       # m^2, interpreted per unit out-of-plane depth
INTERFACE_LENGTH_2D = 2.0    # m, interpreted per unit out-of-plane depth
EPS_P = 1.0
EPS_D = 4.0
REL_TOL = 5.0e-7
UNIFORM_TOL = 5.0e-8
ABS_CHARGE = 2.0e-16
ABS_PHI = 2.0e-7


def close(a: float, b: float, rel: float = REL_TOL, abs_: float = 0.0) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_)


def normalized_residual(residual: float, *scales: float) -> float:
    scale = max(*(abs(x) for x in scales), 1.0e-300)
    return abs(residual) / scale


def poisson_interface_from_measured(q_volume: float, q_surface: float) -> float:
    """1D y-uniform solution for the D6 two-layer geometry.

    q_volume is the integrated plasma volume charge per unit out-of-plane depth [C/m].
    q_surface is the integrated interface charge per unit out-of-plane depth [C/m].
    The plasma and dielectric layers are each 1 m thick and the interface is 2 m long.
    """
    rho = q_volume / PLASMA_VOLUME_2D
    sigma = q_surface / INTERFACE_LENGTH_2D
    source = rho / EPS0
    slope_constant = (
        sigma / EPS0 + source * (1.0 + EPS_D / (2.0 * EPS_P))
    ) / (EPS_P + EPS_D)
    return -source / (2.0 * EPS_P) + slope_constant


def owner_checks(input_path: Path) -> dict[str, bool]:
    text = input_path.read_text(encoding="utf-8")
    return {
        "single_see_functor_owner": text.count("property_name = see_number_flux") == 1,
        "single_net_current_functor_owner": text.count("property_name = net_surface_current_density") == 1,
        "single_sigma_current_owner": text.count("type = PhysicsLowerDSurfaceCurrent") == 1,
        "single_poisson_surface_owner": text.count("type = PhysicsADSurfaceChargePoissonBC") == 1,
        "exactly_two_species_surface_consumers": text.count("type = PhysicsFVLogMolarDielectricFluxBC") == 2,
    }


def main() -> int:
    csv_path = Path(sys.argv[1] if len(sys.argv) > 1 else "d6_2d_integrated_out.csv")
    input_path = Path(sys.argv[2] if len(sys.argv) > 2 else "d6_2d_integrated.i")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(handle)]

    expected_rows = NSTEPS + 1
    checks: dict[str, bool] = {
        "row_count_initial_plus_timesteps": len(rows) == expected_rows,
    }
    diagnostics: dict[str, object] = {
        "per_step": [],
    }

    if len(rows) != expected_rows:
        report = {
            "classification": "D6_2D_DIELECTRIC_INTEGRATED_FAIL",
            "checks": checks,
            "diagnostics": diagnostics,
            "reason": f"expected {expected_rows} CSV rows, got {len(rows)}",
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    initial = rows[0]
    checks.update(owner_checks(input_path))
    checks["initial_neutrality"] = abs(initial["volume_charge"]) <= ABS_CHARGE
    checks["initial_surface_charge_zero"] = abs(initial["surface_charge_total"]) <= ABS_CHARGE
    checks["initial_phi_zero"] = abs(initial["phi_interface"]) <= ABS_PHI
    checks["initial_positive_ion"] = initial["ion_density_min"] > 0.0
    checks["initial_positive_electron"] = initial["electron_density_min"] > 0.0

    all_particle_ledgers = True
    all_surface_ledgers = True
    all_global_ledgers = True
    all_flux_identities = True
    all_gauss = True
    all_positive = True
    all_uniform = True
    all_times = True

    for k, row in enumerate(rows):
        expected_time = k * DT
        all_times &= close(row["time"], expected_time, rel=1.0e-10, abs_=1.0e-16)

        ion_flux_identity = row["ion_flux"] - row["ion_surface_flux"] - row["ion_migration_flux"]
        see_identity = row["see_flux"] - GAMMA * row["ion_flux"]
        electron_identity = row["electron_signed_flux"] - (row["electron_primary_flux"] - row["see_flux"])
        see_current_identity = row["see_current"] - E * row["see_flux"]
        net_current_identity = row["net_surface_current"] - E * (
            row["ion_flux"] - row["electron_signed_flux"]
        )

        flux_ok = (
            normalized_residual(ion_flux_identity, row["ion_flux"], row["ion_surface_flux"], row["ion_migration_flux"]) <= REL_TOL
            and normalized_residual(see_identity, row["see_flux"], GAMMA * row["ion_flux"]) <= REL_TOL
            and normalized_residual(electron_identity, row["electron_signed_flux"], row["electron_primary_flux"], row["see_flux"]) <= REL_TOL
            and normalized_residual(see_current_identity, row["see_current"], E * row["see_flux"]) <= REL_TOL
            and normalized_residual(net_current_identity, row["net_surface_current"], E * row["ion_flux"], E * row["electron_signed_flux"]) <= REL_TOL
        )
        all_flux_identities &= flux_ok

        sigma_scale = max(abs(row["sigma_average"]), abs(row["sigma_min"]), abs(row["sigma_max"]), 1.0e-30)
        sigma_uniform = abs(row["sigma_max"] - row["sigma_min"]) / sigma_scale <= UNIFORM_TOL
        sigma_integral = close(
            row["surface_charge_total"],
            row["sigma_average"] * INTERFACE_LENGTH_2D,
            rel=REL_TOL,
            abs_=ABS_CHARGE,
        )

        ni_scale = max(abs(row["ion_density_min"]), abs(row["ion_density_max"]), 1.0)
        ne_scale = max(abs(row["electron_density_min"]), abs(row["electron_density_max"]), 1.0)
        density_uniform = (
            abs(row["ion_density_max"] - row["ion_density_min"]) / ni_scale <= UNIFORM_TOL
            and abs(row["electron_density_max"] - row["electron_density_min"]) / ne_scale <= UNIFORM_TOL
        )
        all_uniform &= sigma_uniform and sigma_integral and density_uniform

        positive = (
            math.isfinite(row["ion_density_min"])
            and math.isfinite(row["electron_density_min"])
            and row["ion_density_min"] > 0.0
            and row["electron_density_min"] > 0.0
        )
        all_positive &= positive

        phi_expected = poisson_interface_from_measured(row["volume_charge"], row["surface_charge_total"])
        gauss_ok = close(row["phi_interface"], phi_expected, rel=REL_TOL, abs_=ABS_PHI)
        all_gauss &= gauss_ok

        step_diag: dict[str, float | int | bool] = {
            "step": k,
            "time_s": row["time"],
            "flux_identity_pass": flux_ok,
            "uniformity_pass": sigma_uniform and sigma_integral and density_uniform,
            "positivity_pass": positive,
            "phi_interface_V": row["phi_interface"],
            "phi_interface_expected_V": phi_expected,
            "volume_charge_C_per_m": row["volume_charge"],
            "surface_charge_C_per_m": row["surface_charge_total"],
            "net_surface_current_A_per_m": row["net_surface_current"],
            "ion_migration_flux_per_m_s": row["ion_migration_flux"],
        }

        if k > 0:
            prev = rows[k - 1]
            d_ni = row["ion_inventory"] - prev["ion_inventory"]
            d_ne = row["electron_inventory"] - prev["electron_inventory"]
            d_qv = row["volume_charge"] - prev["volume_charge"]
            d_qs = row["surface_charge_total"] - prev["surface_charge_total"]

            ion_ledger = d_ni + DT * row["ion_flux"]
            electron_ledger = d_ne + DT * row["electron_signed_flux"]
            surface_ledger = d_qs - DT * row["net_surface_current"]
            global_ledger = d_qv + d_qs

            ion_ok = normalized_residual(ion_ledger, d_ni, DT * row["ion_flux"]) <= REL_TOL
            electron_ok = normalized_residual(electron_ledger, d_ne, DT * row["electron_signed_flux"]) <= REL_TOL
            surface_ok = normalized_residual(surface_ledger, d_qs, DT * row["net_surface_current"]) <= REL_TOL
            global_ok = abs(global_ledger) <= ABS_CHARGE or normalized_residual(global_ledger, d_qv, d_qs) <= REL_TOL

            all_particle_ledgers &= ion_ok and electron_ok
            all_surface_ledgers &= surface_ok
            all_global_ledgers &= global_ok

            step_diag.update({
                "ion_particle_ledger": ion_ledger,
                "electron_particle_ledger": electron_ledger,
                "surface_charge_ledger_C_per_m": surface_ledger,
                "global_charge_ledger_C_per_m": global_ledger,
                "particle_ledger_pass": ion_ok and electron_ok,
                "surface_ledger_pass": surface_ok,
                "global_ledger_pass": global_ok,
            })

        diagnostics["per_step"].append(step_diag)

    final = rows[-1]
    final_global = (final["volume_charge"] - initial["volume_charge"]) + (
        final["surface_charge_total"] - initial["surface_charge_total"]
    )

    checks.update({
        "time_grid": all_times,
        "particle_ledgers_all_steps": all_particle_ledgers,
        "surface_charge_ledgers_all_steps": all_surface_ledgers,
        "global_charge_ledgers_all_steps": all_global_ledgers,
        "flux_owner_identities_all_steps": all_flux_identities,
        "gauss_interface_consistency_all_steps": all_gauss,
        "electron_heavy_positivity_all_steps": all_positive,
        "multi_segment_uniformity_all_steps": all_uniform,
        "finite_see_active": final["see_flux"] > 0.0 and final["see_current"] > 0.0,
        "dynamic_surface_charge_active": abs(final["surface_charge_total"]) > 1.0e-14,
        "electrostatic_feedback_active": abs(final["phi_interface"]) > 1.0e-3,
        "ion_migration_feedback_active": (
            final["ion_migration_flux"] > 0.0
            and final["ion_migration_flux"] / max(abs(final["ion_surface_flux"]), 1.0) > 1.0e-4
        ),
        "final_global_charge_ledger": abs(final_global) <= ABS_CHARGE,
    })

    passed = all(checks.values())
    diagnostics["final"] = {
        "time_s": final["time"],
        "ion_density_min_m3": final["ion_density_min"],
        "electron_density_min_m3": final["electron_density_min"],
        "see_flux_per_m_s": final["see_flux"],
        "net_surface_current_A_per_m": final["net_surface_current"],
        "surface_charge_C_per_m": final["surface_charge_total"],
        "sigma_average_C_m2": final["sigma_average"],
        "phi_interface_V": final["phi_interface"],
        "ion_migration_flux_per_m_s": final["ion_migration_flux"],
        "final_global_charge_ledger_C_per_m": final_global,
    }

    report = {
        "classification": "D6_2D_DIELECTRIC_INTEGRATED_PASS" if passed else "D6_2D_DIELECTRIC_INTEGRATED_FAIL",
        "scope": "2D, unit out-of-plane depth; finite SEE + dynamic lower-D sigma_s + FEM Poisson feedback + ion wall migration feedback",
        "verification_parameters": {
            "see_gamma": GAMMA,
            "ion_mobility_m2_V_s": 1.0,
            "dt_s": DT,
            "timesteps": NSTEPS,
        },
        "checks": checks,
        "diagnostics": diagnostics,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
