from __future__ import annotations

import math
from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall.charged import (
    FARADAY_C_PER_MOL,
    _validated_parameters as validate_a3e,
)
from physics_harness.application.experiment_spec import load_experiment_spec

ROOT = Path(__file__).resolve().parents[2]
A2_SPEC = ROOT / "experiments/Issue27_surface_reactions/A2_om_neutralization/experiment.json"
A3_SPEC = ROOT / "experiments/Issue27_surface_reactions/A3_positive_ion_neutralization/experiment.json"
A3E_SPEC = ROOT / "experiments/Issue27_surface_reactions/A3e_charged_wall_ledger/experiment.json"


def test_issue27_a3e_composes_accepted_a2_a3_prescribed_rates() -> None:
    a2 = load_experiment_spec(A2_SPEC)
    a3 = load_experiment_spec(A3_SPEC)
    a3e = load_experiment_spec(A3E_SPEC)
    frozen = validate_a3e(a3e.parameters)

    assert math.isclose(
        float(frozen["Om_event_flux_mol_m2_s"]),
        float(a2.parameters["Om_event_flux_mol_m2_s"]),
        rel_tol=0.0,
        abs_tol=0.0,
    )
    assert math.isclose(
        float(frozen["O2p_event_flux_mol_m2_s"]),
        float(a3.parameters["O2p_event_flux_mol_m2_s"]),
        rel_tol=0.0,
        abs_tol=0.0,
    )
    assert math.isclose(
        float(frozen["Op_event_flux_mol_m2_s"]),
        float(a3.parameters["Op_event_flux_mol_m2_s"]),
        rel_tol=0.0,
        abs_tol=0.0,
    )
    assert float(frozen["secondary_emission_coefficient"]) == 0.0

    r_o2p = float(frozen["O2p_event_flux_mol_m2_s"])
    r_op = float(frozen["Op_event_flux_mol_m2_s"])
    r_om = float(frozen["Om_event_flux_mol_m2_s"])
    r_e = float(frozen["electron_absorption_molar_flux_mol_m2_s"])

    assert math.isclose(r_e, r_o2p + r_op - r_om, rel_tol=0.0, abs_tol=0.0)
    assert math.isclose(
        FARADAY_C_PER_MOL * (r_o2p + r_op - r_om - r_e),
        0.0,
        rel_tol=0.0,
        abs_tol=1.0e-18,
    )
