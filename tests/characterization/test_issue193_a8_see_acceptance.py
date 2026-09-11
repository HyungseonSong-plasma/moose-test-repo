from __future__ import annotations

import json

from experiments.Issue193_a8_see_acceptance import run as acceptance
from physics_harness.application.experiment_spec import load_experiment_spec


def test_issue193_tolerances_are_predeclared_and_bounded() -> None:
    assert acceptance.ALGEBRAIC_REL_TOL == 1.0e-10
    assert acceptance.RUNTIME_REL_TOL == 1.0e-3
    assert acceptance.COMPOSITION_ABS_TOL == 1.0e-8
    assert acceptance.ZERO_ABS_TOL == 1.0e-12
    assert acceptance.ELECTRON_DENSITY_FLOOR == -1.0e-12


def test_issue193_construction_audit_closes_frozen_see_ownership() -> None:
    spec = load_experiment_spec(acceptance.A8_SPEC)
    audit = acceptance._construction_audit(spec.parameters)
    assert audit["status"] == "PASS"
    checks = audit["checks"]
    for key in (
        "gamma_O2p_exact",
        "gamma_Op_exact",
        "energy_4eV_exact",
        "see_factor_plus_one",
        "see_factor_zero_control",
        "O2p_surface_once",
        "O2p_migration_once",
        "Op_surface_once",
        "Op_migration_once",
        "Om_absent_from_functors",
        "Om_absent_from_expression",
        "energy_scale_4eV",
    ):
        assert checks[key] is True


def test_issue193_analyzer_detects_owned_negative_mutations() -> None:
    spec = load_experiment_spec(acceptance.A8_SPEC)
    construction = acceptance._construction_audit(spec.parameters)
    metrics = acceptance._synthetic_metrics()
    decision = acceptance._evaluate_gates(construction, metrics, runtime_ok=True)
    assert decision["scientific_hard_pass"] is True

    bad = json.loads(json.dumps(metrics))
    bad["see_on"]["see_particle_rate_relative_defect"] = 1.0e-2
    assert acceptance._evaluate_gates(construction, bad, runtime_ok=True)["gates"][
        "G03_see_total_magnitude"
    ] is False

    bad = json.loads(json.dumps(metrics))
    bad["see_on"]["measured_electron_inventory_delta"] = -20.0
    assert acceptance._evaluate_gates(construction, bad, runtime_ok=True)["gates"][
        "G02_see_source_direction"
    ] is False

    bad_construction = json.loads(json.dumps(construction))
    bad_construction["checks"]["Om_absent_from_expression"] = False
    assert acceptance._evaluate_gates(
        bad_construction, metrics, runtime_ok=True
    )["gates"]["G06_Om_zero_see"] is False
