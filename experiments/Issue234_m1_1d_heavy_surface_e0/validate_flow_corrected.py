#!/usr/bin/env python3
"""Validate Issue #234 1D E=0 heavy-flow + independent electron wall-loss discriminator."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input_flow_corrected.i"
CSV = ROOT / "input_flow_corrected_out.csv"

P_PA = 1.33322
TG_K = 300.0
END_S = 1.0e-8
Q_SCCM = 20.0
M_INLET = 0.032
VM_STD = 0.0224136
MDOT_EXPECTED = Q_SCCM * 1.0e-6 / 60.0 * M_INLET / VM_STD
N_E0 = 1.0e18


def static_contract() -> dict[str, bool]:
    text = INPUT.read_text(encoding="utf-8")
    all_species = "mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'"
    all_diff = "diffusivities = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'"
    return {
        "one_dimensional": "dim = 1" in text,
        "pressure_10mTorr": "outlet_pressure = 1.33322" in text,
        "gas_temperature_300K": "prop_values = '300.0 1.33322" in text,
        "flow_solved": all(tok in text for tok in (
            "type = INSFVVelocityVariable",
            "type = INSFVPressureVariable",
            "type = INSFVRhieChowInterpolator",
            "type = INSFVMassAdvection",
            "type = INSFVMomentumAdvection",
            "type = INSFVMomentumDiffusion",
            "type = INSFVMomentumPressure",
        )),
        "right_20sccm_inlet": all(tok in text for tok in (
            "Q_sccm = 20",
            "M_inlet = 0.032",
            "type = WCNSFVMassFluxBC",
            "boundary = right",
            "direction = '-1 0 0'",
        )),
        "left_pressure_outlet": "type = INSFVOutletPressureBC" in text and "boundary = left" in text,
        "pure_O2_inlet_for_solved_species": text.count("type = WCNSFVScalarFluxBC") == 6 and text.count("default = 0") >= 6,
        "no_heavy_surface_reactions": all(tok not in text for tok in (
            "[O_surface_loss]", "[O2s_surface_loss]", "[Os_surface_loss]",
            "[O2p_surface_loss]", "[Om_surface_loss]", "[Op_surface_loss]",
            "[O_neutralization_return]",
        )),
        "no_poisson": "PhysicsFVPoisson" not in text and "potential_plasma" not in text,
        "zero_electric_field": all(tok in text for tok in (
            "[phi_zero]",
            "expression = '0.0*x'",
            "type = PhysicsFVLogMolarElectrostaticDrift",
            "potential = phi_zero",
            "charge_number = -1",
            "boundaries_to_avoid = 'left right'",
        )),
        "no_heavy_electric_migration": "Electromigration" not in text and "ion_migration" not in text,
        "no_bulk_chemistry": "ReactionSource" not in text,
        "no_see": "electron_see" not in text and "secondary" not in text.lower() and "0.05*(" not in text,
        "electron_diffusion_previous_contract": all(tok in text for tok in (
            "type = PhysicsFVLogMolarElectronDiffusion",
            "coeff = electron_diffusion",
            "coeff_interp_method = harmonic",
            "41257.29899041419",
        )),
        "electron_thermal_wall_loss_on": all(tok in text for tok in (
            "property_name = thermal_flux_molar_outward",
            "0.25*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))",
            "[right_thermal_surface_loss]",
            "variable = log_e",
            "functor = thermal_flux_molar_outward",
            "factor = -1",
        )),
        "electron_not_advected_by_heavy_flow": "PhysicsFVLogMolarElectronAdvection" not in text,
        "heavy_transport_registered": "type = PhysicsThermalDiffusionMaterial" in text,
        "heavy_advection_on": text.count("type = PhysicsFVMassFractionAdvection") == 6,
        "heavy_corrected_diffusion_on": text.count("type = PhysicsFVHeavyMassCorrectedDiffusion") == 6,
        "all_species_in_correction": text.count(all_species) >= 7,
        "all_diffusivities_in_correction": text.count(all_diff) == 6,
        "mass_fraction_constraint": "expression = '1.0-s1-s2-s3-s4-s5-s6'" in text,
        "automatic_scaling_off": "automatic_scaling = false" in text,
    }


def main() -> int:
    checks = static_contract()
    failed_static = sorted(k for k, ok in checks.items() if not ok)
    if failed_static:
        raise SystemExit(f"static contract failed: {failed_static}")

    rows = list(csv.DictReader(CSV.open(newline="", encoding="utf-8")))
    if len(rows) < 2:
        raise SystemExit("need INITIAL and TIMESTEP_END rows")
    initial, final = rows[0], rows[-1]

    required = (
        "time", "inlet_area", "inlet_mdot", "inlet_mass_actual", "outlet_mass_actual",
        "outlet_p_avg", "electron_inventory", "n_e_min", "n_e_max",
        "wall_thermal_flux_rate_per_area", "wall_thermal_loss_integral_per_area",
        "sum_w_min", "sum_w_max", "O2_min", "u_min", "u_max", "p_min", "p_max",
    )
    missing = [name for name in required if name not in final]
    if missing:
        raise SystemExit(f"missing CSV columns: {missing}")

    v0 = {k: float(initial[k]) for k in required}
    vf = {k: float(final[k]) for k in required}
    if not all(math.isfinite(x) for x in (*v0.values(), *vf.values())):
        raise SystemExit("non-finite postprocessor value")

    def close(a: float, b: float, rel: float = 2e-7, abs_: float = 1e-15) -> bool:
        return math.isclose(a, b, rel_tol=rel, abs_tol=abs_)

    inventory_loss = v0["electron_inventory"] - vf["electron_inventory"]
    wall_loss = vf["wall_thermal_loss_integral_per_area"]
    electron_ledger_rel = abs(inventory_loss - wall_loss) / max(abs(inventory_loss), abs(wall_loss), 1e-30)

    runtime_checks = {
        "final_time": close(vf["time"], END_S, rel=0.0, abs_=1e-18),
        "sccm_to_mdot": close(vf["inlet_mdot"], MDOT_EXPECTED, rel=2e-8, abs_=1e-18),
        "inlet_area_positive": vf["inlet_area"] > 0.0,
        "right_inlet_direction_negative_x": vf["inlet_mass_actual"] < 0.0,
        "left_outlet_direction": vf["outlet_mass_actual"] > 0.0,
        "steady_mass_flow_closure": abs(vf["outlet_mass_actual"] - MDOT_EXPECTED) / MDOT_EXPECTED < 2e-2,
        "left_pressure_10mTorr": close(vf["outlet_p_avg"], P_PA, rel=5e-3, abs_=1e-10),
        "velocity_negative_x": vf["u_min"] < 0.0 and vf["u_max"] < 0.0,
        "pressure_positive": vf["p_min"] > 0.0 and vf["p_max"] > 0.0,
        "sum_w_min_one": close(vf["sum_w_min"], 1.0, rel=0.0, abs_=1e-10),
        "sum_w_max_one": close(vf["sum_w_max"], 1.0, rel=0.0, abs_=1e-10),
        "O2_positive": vf["O2_min"] > 0.0,
        "electron_density_positive": vf["n_e_min"] > 0.0,
        "electron_inventory_decreases": vf["electron_inventory"] < v0["electron_inventory"],
        "electron_wall_flux_positive": vf["wall_thermal_flux_rate_per_area"] > 0.0,
        "electron_wall_loss_positive": wall_loss > 0.0,
        "electron_gradient_present": vf["n_e_min"] < vf["n_e_max"],
        "electron_below_initial_density": vf["n_e_max"] < N_E0,
        "electron_particle_ledger": electron_ledger_rel < 2e-6,
    }
    failed_runtime = sorted(k for k, ok in runtime_checks.items() if not ok)

    summary = {
        "status": "PASS" if not failed_runtime else "FAIL",
        "claim_scope": "1D E=0 independent electron diffusion + pure thermal right-wall loss together with right 20 sccm O2 heavy-flow inlet, left 10 mTorr outlet, and corrected heavy diffusion",
        "gas": {"pressure_Pa": P_PA, "pressure_mTorr": 10.0, "temperature_K": TG_K},
        "inlet": {"side": "right", "flow_sccm": Q_SCCM, "M_kg_per_mol": M_INLET, "expected_mdot_kg_per_s": MDOT_EXPECTED},
        "outlet": {"side": "left", "pressure_Pa": P_PA},
        "electron": {
            "heavy_flow_advection": False,
            "diffusion": True,
            "electric_field": 0.0,
            "pure_thermal_right_wall_loss": True,
            "inventory_loss_mol_per_m2": inventory_loss,
            "integrated_wall_loss_mol_per_m2": wall_loss,
            "ledger_relative_error": electron_ledger_rel,
        },
        "see": False,
        "bulk_chemistry": False,
        "heavy_surface_reactions": False,
        "diffusion_mass_frame_contract": "J_k = J_k_raw - w_k*sum_j(J_j_raw); sum_k J_k = 0 when sum_k w_k = 1",
        "static_checks": checks,
        "runtime_checks": runtime_checks,
        "final": vf,
        "failed_runtime_checks": failed_runtime,
        "science_claim": False,
        "timestep_convergence_claim": False,
    }
    (ROOT / "validation_flow_corrected_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if failed_runtime:
        raise SystemExit(f"runtime validation failed: {failed_runtime}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
