#!/usr/bin/env python3
"""Validate Issue #234 1D E=0 flow + corrected heavy diffusion + surface reactions."""
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


def static_contract() -> dict[str, bool]:
    text = INPUT.read_text(encoding="utf-8")
    all_species = "mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'"
    all_diff = "diffusivities = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'"
    return {
        "one_dimensional": "dim = 1" in text,
        "pressure_10mTorr": "1.33322" in text,
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
        "flow_unforced_zero_baseline": "boundary = 'left right'" in text and "function = 1.33322" in text,
        "no_poisson": "PhysicsFVPoisson" not in text and "potential_plasma" not in text,
        "no_electric_motion": all(tok not in text for tok in (
            "ElectrostaticDrift", "Electromigration", "ion_migration", "phi_zero"
        )),
        "no_bulk_chemistry": "ReactionSource" not in text,
        "no_see": "electron_see" not in text and "secondary" not in text.lower() and "0.05*(" not in text,
        "electron_diffusion_on": "type = PhysicsFVLogMolarElectronDiffusion" in text,
        "heavy_transport_registered": "type = PhysicsThermalDiffusionMaterial" in text,
        "heavy_advection_on": text.count("type = PhysicsFVMassFractionAdvection") == 6,
        "heavy_corrected_diffusion_on": text.count("type = PhysicsFVHeavyMassCorrectedDiffusion") == 6,
        "all_species_in_correction": text.count(all_species) >= 7,
        "all_diffusivities_in_correction": text.count(all_diff) == 6,
        "mass_fraction_constraint": "expression = '1.0-s1-s2-s3-s4-s5-s6'" in text,
        "thermal_electron_loss_on": "[electron_thermal_loss]" in text,
        "neutral_surface_network": all(tok in text for tok in (
            "[O_surface_loss]", "[O2s_surface_loss]", "[Os_surface_loss]"
        )),
        "charged_surface_network_thermal_only": all(tok in text for tok in (
            "[O2p_surface_loss]", "[Om_surface_loss]", "[Op_surface_loss]"
        )),
        "neutralization_return": "[O_neutralization_return]" in text,
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
        "time", "electron_inventory", "electron_thermal_rate", "electron_thermal_integral",
        "sum_w_min", "sum_w_max", "O2_min", "u_min", "u_max", "p_min", "p_max",
        "O_surface_rate", "O2s_surface_rate", "Os_surface_rate",
        "O2p_surface_rate", "Om_surface_rate", "Op_surface_rate",
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

    measured_electron_loss = v0["electron_inventory"] - vf["electron_inventory"]
    expected_electron_loss = vf["electron_thermal_integral"]

    runtime_checks = {
        "final_time": close(vf["time"], END_S, rel=0.0, abs_=1e-18),
        "sum_w_min_one": close(vf["sum_w_min"], 1.0, rel=0.0, abs_=1e-10),
        "sum_w_max_one": close(vf["sum_w_max"], 1.0, rel=0.0, abs_=1e-10),
        "O2_positive": vf["O2_min"] > 0.0,
        "electron_inventory_positive": vf["electron_inventory"] > 0.0,
        "thermal_electron_loss_positive": vf["electron_thermal_rate"] > 0.0,
        "electron_particle_ledger": close(measured_electron_loss, expected_electron_loss),
        "flow_velocity_zero": max(abs(vf["u_min"]), abs(vf["u_max"])) < 1e-10,
        "pressure_uniform_10mTorr": close(vf["p_min"], P_PA, rel=0.0, abs_=1e-8) and close(vf["p_max"], P_PA, rel=0.0, abs_=1e-8),
        "O_surface_active": vf["O_surface_rate"] > 0.0,
        "O2s_surface_active": vf["O2s_surface_rate"] > 0.0,
        "Os_surface_active": vf["Os_surface_rate"] > 0.0,
        "O2p_surface_active": vf["O2p_surface_rate"] > 0.0,
        "Om_surface_active": vf["Om_surface_rate"] > 0.0,
        "Op_surface_active": vf["Op_surface_rate"] > 0.0,
    }
    failed_runtime = sorted(k for k, ok in runtime_checks.items() if not ok)

    summary = {
        "status": "PASS" if not failed_runtime else "FAIL",
        "claim_scope": "1D E=0 solved gas flow + corrected heavy diffusion + surface reactions; electron diffusion + thermal loss; SEE off",
        "gas": {"pressure_Pa": P_PA, "pressure_mTorr": 10.0, "temperature_K": TG_K},
        "electric_motion": False,
        "see": False,
        "bulk_chemistry": False,
        "diffusion_mass_frame_contract": "J_k = J_k_raw - w_k*sum_j(J_j_raw); sum_k J_k = 0 when sum_k w_k = 1",
        "static_checks": checks,
        "runtime_checks": runtime_checks,
        "electron_ledger": {
            "initial_inventory_mol_m2": v0["electron_inventory"],
            "final_inventory_mol_m2": vf["electron_inventory"],
            "measured_loss_mol_m2": measured_electron_loss,
            "thermal_loss_integral_mol_m2": expected_electron_loss,
        },
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
