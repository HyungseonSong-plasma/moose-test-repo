#!/usr/bin/env python3
"""Issue #331 Stage-B source-owner inventory.

This script renders the accepted #306 Sequence08 ratio4 case in-memory and
fails closed unless all source anchors required by the monolithic charged
splice are present.  It does not mutate the accepted source and deliberately
does not consume any #310 Sequence09/10 experiment.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue306_heavy_charge_motion import wall08_control as seq08


def require(text: str, token: str, owner: str) -> None:
    if token not in text:
        raise RuntimeError(f"missing accepted {owner} anchor: {token!r}")


def main() -> None:
    spec = next(x for x in seq08.SPECS if int(x["ratio"]) == 4)
    p = seq08._params(spec)
    parent, fast, poisson = seq08._render_case(spec, p)

    # Accepted electron/energy owners that must move into the single problem.
    for token in (
        "[log_e]",
        "[n_epsilon]",
        "PhysicsFVElectronEnergyJouleHeating",
        "potential_from_poisson",
        "electron_sheath_factor",
        "right_thermal_surface_loss",
        "right_energy_surface_loss",
    ):
        require(fast, token, "electron")

    # Accepted charged-heavy owners.  The Stage-B splice must preserve every
    # transport mechanism, not collapse ions to pure E-drift + diffusion.
    counts = {
        "heavy_time": parent.count("type = PhysicsFVConservativeMassFractionTimeDerivative"),
        "heavy_advection": parent.count("type = PhysicsFVMassFractionAdvection"),
        "heavy_diffusion": parent.count("type = PhysicsFVMixtureAveragedDiffusion"),
        "ion_drift": parent.count("type = PhysicsFVElectrostaticDrift"),
        "mass_frame_correction": parent.count("type = PhysicsFVHeavyMassElectromigrationCorrection"),
    }
    expected = {
        "heavy_time": 6,
        "heavy_advection": 6,
        "heavy_diffusion": 6,
        "ion_drift": 3,
        "mass_frame_correction": 6,
    }
    if counts != expected:
        raise RuntimeError(f"accepted heavy-owner counts changed: {counts} != {expected}")
    for token in ("[w_O2p]", "[w_Om]", "[w_Op]", "potential_fast"):
        require(parent, token, "charged-heavy")

    # The current Poisson child is structural source only.  Its frozen charge
    # ownership is specifically forbidden in the monolithic output.
    for token in (
        "potential_plasma",
        "log_e_frozen",
        "w_O2p_frozen",
        "w_Om_frozen",
        "w_Op_frozen",
        "FVCoupledForce",
    ):
        require(poisson, token, "Poisson")

    forbidden_output = [
        "potential_from_poisson",
        "potential_fast",
        "log_e_frozen",
        "w_O2p_frozen",
        "w_Om_frozen",
        "w_Op_frozen",
        "FullSolveMultiApp",
        "fixed_point_max_its",
    ]

    result = {
        "status": "PASS",
        "issue": 331,
        "source": "Issue306 Sequence08 ratio4",
        "source_commit": "1b28a1bccbec4ccad5e597500142a7e7e06ef4a3",
        "chi_e": p["chi_e"],
        "chi_h": p["chi_h"],
        "ratio": p["heavy_to_electron_dt_ratio"],
        "charged_unknowns": ["log_e", "n_epsilon", "w_O2p", "w_Om", "w_Op", "potential_plasma"],
        "accepted_heavy_owner_counts": counts,
        "forbidden_in_monolithic_output": forbidden_output,
        "next": "construct monolithic_charged.i by moving these exact owners into one nonlinear problem",
    }
    print("ISSUE331_SPLICE_INVENTORY: PASS")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
