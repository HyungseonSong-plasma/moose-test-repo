#!/usr/bin/env python3
"""Issue47 characterization for the accepted Issue46 FD-reference harness.

This is a test-only characterization surface. It freezes accepted Issue46
behavior and the false-PASS/structural controls required by the refactor.
Production code must not import this module.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import augmented_jacobian_localization as loc
from qpx_harness import electron_inventory_nullspace as inv
from qpx_harness import jacobian_fd_reference_audit as base
from qpx_harness import petsc_first_linear_diagnostic as first_linear
from qpx_harness.moose_input import MooseInput


ACCEPTED_EVR1_ELECTRON_DOF_COUNT = 2348
ACCEPTED_EVR1_OBSERVED_ATTENUATION = 0.96406286
ACCEPTED_EVR2_REL_ERROR = 5.35565e-11
ACCEPTED_FINAL_CLASS = "FD_REFERENCE_QUANTIZATION_CONFIRMED"
ACCEPTED_WP_PREDICTED_ATTENUATION = 0.9640628864075022


class CharacterizationFailure(AssertionError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CharacterizationFailure(message)


def _expect_dofmap_rejection(text: str, expected_fragment: str) -> None:
    try:
        loc.parse_dof_map_text(text)
    except loc.AugmentedJacobianLocalizationError as exc:
        _require(
            expected_fragment in str(exc),
            f"DOFMap rejection mismatch: expected {expected_fragment!r}, got {exc!s}",
        )
        return
    raise CharacterizationFailure(
        f"DOFMap mutation unexpectedly passed: expected {expected_fragment!r}"
    )


def _fixed_c0_fixture() -> str:
    """Build the accepted Issue46 synthetic C0 fixture from its canonical owner."""
    return base._issue46_synthetic_constrained_input(base.TARGET)


def _remove_parameter_line(text: str, path: str, name: str) -> str:
    """Test-only mutation: remove exactly one parameter assignment from one block."""
    doc = MooseInput(text)
    span = doc.unique(path)
    block = text[span.start : span.end]
    pattern = re.compile(
        rf"(?m)^[ \t]*{re.escape(name)}[ \t]*=[^\r\n]*(?:\r?\n|$)"
    )
    matches = list(pattern.finditer(block))
    if len(matches) != 1:
        raise CharacterizationFailure(
            f"expected one {path}/{name} assignment, found {len(matches)}"
        )
    match = matches[0]
    start = span.start + match.start()
    end = span.start + match.end()
    mutated = text[:start] + text[end:]
    MooseInput(mutated)
    return mutated


def _baseline_and_ds(fixture_text: str) -> tuple[str, str]:
    first_text, _ = first_linear.instrument_first_linear(fixture_text)
    baseline, _ = loc.instrument_localization(first_text)
    ds_text, _ = base.instrument_ds_reference(baseline)
    return baseline, ds_text


def _dofmap_for_counts(electron_dofs: int, potential_dofs: int | None = None) -> str:
    if electron_dofs <= 0:
        raise CharacterizationFailure("electron_dofs must be positive")
    if potential_dofs is None:
        potential_dofs = electron_dofs
    if potential_dofs <= 0:
        raise CharacterizationFailure("potential_dofs must be positive")
    potential_start = electron_dofs
    potential_stop = potential_start + potential_dofs
    scalar_dof = potential_stop
    return json.dumps(
        {
            "ndof": scalar_dof + 1,
            "vars": [
                {
                    "name": "n_e",
                    "subdomains": [{"id": 1, "dofs": list(range(electron_dofs))}],
                },
                {
                    "name": "potential_plasma",
                    "subdomains": [
                        {"id": 1, "dofs": list(range(potential_start, potential_stop))}
                    ],
                },
                {
                    "name": inv.LAMBDA_VARIABLE,
                    "subdomains": [{"id": 1, "dofs": []}],
                },
            ],
        }
    )


def _historical_evr2_dofmap() -> str:
    """Accepted-vector fixture: historical topology only, never runtime configuration."""
    return _dofmap_for_counts(ACCEPTED_EVR1_ELECTRON_DOF_COUNT)


def _identity_pass() -> dict[str, str]:
    return {
        "status": "PASS",
        "class": "ISSUE46_EXPERIMENT_IDENTITY_PASS",
        "reason": "accepted-vector characterization explicitly supplies Issue46 identity",
    }


def _identity_drift() -> dict[str, str]:
    return {
        "status": "HOLD",
        "class": "ISSUE46_EXPERIMENT_IDENTITY_DRIFT",
        "reason": "synthetic topology is analyzer-valid but not the accepted experiment",
    }


def _applicability_pass() -> dict[str, str]:
    return {
        "status": "PASS",
        "class": "PETSC_WP_MECHANISM_APPLICABILITY_PASS",
        "reason": "accepted-vector characterization uses the accepted PETSc realization",
    }


def _applicability_hold() -> dict[str, str]:
    return {
        "status": "HOLD",
        "class": "PETSC_WP_MECHANISM_APPLICABILITY_UNRESOLVED",
        "reason": "runtime PETSc realization is intentionally unresolved",
    }


def _check_predictor() -> None:
    historical_vector_norm = (
        math.sqrt(float(ACCEPTED_EVR1_ELECTRON_DOF_COUNT)) * abs(base.TARGET)
    )
    prediction = base.predict_fd_step_quantization(
        vector_norm=historical_vector_norm,
        component_value=base.TARGET,
    )
    _require(
        abs(
            prediction["wp_predicted_attenuation"]
            - ACCEPTED_WP_PREDICTED_ATTENUATION
        )
        <= 1.0e-12,
        "accepted WP predictor value drifted",
    )
    _require(
        abs(
            prediction["wp_predicted_attenuation"]
            - ACCEPTED_EVR1_OBSERVED_ATTENUATION
        )
        <= 1.0e-6,
        "accepted WP mechanism no longer agrees with the historical observation",
    )
    _require(
        abs(prediction["ds_predicted_attenuation"] - 1.0)
        <= base.DS_ATTENUATION_TO_UNITY_TOL,
        "accepted DS representability drifted",
    )

    vector_norm = 123.0
    component_value = 7.0
    explicit = base.predict_fd_step_quantization(
        vector_norm=vector_norm,
        component_value=component_value,
    )
    expected_wp = math.sqrt(1.0 + vector_norm) * base.SQRT_MACHINE_EPSILON
    expected_ds = component_value * base.SQRT_MACHINE_EPSILON
    _require(
        explicit["wp_requested_dx"] == expected_wp,
        "WP predictor did not use the explicit vector norm",
    )
    _require(
        explicit["ds_requested_dx"] == expected_ds,
        "DS predictor did not use the explicit component value",
    )


def _check_structural_zero_and_directions() -> None:
    raw = {
        "threshold": base.LOCALIZATION_THRESHOLD,
        "entries": [
            {"row": 0, "col": 0, "value": 0.0},
            {"row": 4, "col": 0, "value": 2.0e-4},
        ],
        "section_observed": True,
    }
    filtered = base.nonzero_threshold_difference(raw)
    _require(filtered["structural_entry_count"] == 2, "structural count drifted")
    _require(
        filtered["nonzero_thresholded_entry_count"] == 1,
        "explicit structural zero was counted as a nonzero mismatch",
    )

    dofmap = base._synthetic_dofmap()
    j_lambda_n = base.directional_localization(
        base._synthetic_log(
            4.0e-5,
            ["row 0: (4, 0.0)", "row 4: (0, 2.0e-4)"],
        ),
        dofmap,
    )
    _require(
        j_lambda_n["metrics"]["j_lambda_n"]["count"] == 1,
        "J_lambda,n direction was not localized",
    )
    _require(
        j_lambda_n["metrics"]["j_n_lambda"]["count"] == 0,
        "zero J_n,lambda entry was miscounted",
    )

    j_n_lambda = base.directional_localization(
        base._synthetic_log(
            4.0e-5,
            ["row 0: (4, 3.0e-4)"],
        ),
        dofmap,
    )
    _require(
        j_n_lambda["metrics"]["j_n_lambda"]["count"] == 1,
        "J_n,lambda direction was not localized",
    )
    _require(
        j_n_lambda["metrics"]["j_lambda_n"]["count"] == 0,
        "J_n,lambda mutation leaked into J_lambda,n",
    )


def _check_dofmap_negative_controls() -> None:
    _expect_dofmap_rejection("{", "invalid DOFMap JSON")

    overlap = json.dumps(
        {
            "ndof": 5,
            "vars": [
                {"name": "n_e", "subdomains": [{"id": 1, "dofs": [0, 1, 2]}]},
                {
                    "name": "potential_plasma",
                    "subdomains": [{"id": 1, "dofs": [2, 3]}],
                },
                {
                    "name": inv.LAMBDA_VARIABLE,
                    "subdomains": [{"id": 1, "dofs": []}],
                },
            ],
        }
    )
    _expect_dofmap_rejection(overlap, "DOFMap variable overlap")

    unmapped = json.dumps(
        {
            "ndof": 6,
            "vars": [
                {"name": "n_e", "subdomains": [{"id": 1, "dofs": [0, 1]}]},
                {
                    "name": "potential_plasma",
                    "subdomains": [{"id": 1, "dofs": [2, 3]}],
                },
                {
                    "name": inv.LAMBDA_VARIABLE,
                    "subdomains": [{"id": 1, "dofs": []}],
                },
            ],
        }
    )
    _expect_dofmap_rejection(unmapped, "cannot resolve scalar DOFs")


def _check_ds_structure_controls() -> None:
    fixture = _fixed_c0_fixture()
    baseline, ds_text = _baseline_and_ds(fixture)

    accepted = base.audit_ds_reference_structure(baseline, ds_text)
    _require(
        accepted["status"] == "PASS",
        "accepted DS-only observation mutation no longer passes",
    )

    missing_c0 = _remove_parameter_line(
        fixture, "Variables/n_e", "initial_condition"
    )
    missing_baseline, missing_ds = _baseline_and_ds(missing_c0)
    missing_report = base.audit_ds_reference_structure(
        missing_baseline, missing_ds
    )
    blocker_ids = {item["id"] for item in missing_report["blockers"]}
    _require(
        missing_report["status"] == "HOLD",
        "missing C0 initial condition unexpectedly passed",
    )
    _require(
        "c0-electron-initial-state" in blocker_ids,
        "missing C0 initial condition did not emit c0-electron-initial-state blocker",
    )

    material_mutation = loc._upsert_petsc_value(ds_text, "-pc_type", "jacobi")
    material_report = base.audit_ds_reference_structure(
        baseline, material_mutation
    )
    _require(
        material_report["status"] == "HOLD",
        "material PETSc option mutation unexpectedly passed",
    )


def _check_runtime_topology_not_historical_literal() -> None:
    nonhistorical_dofs = 3
    result = base.analyze_ds_runtime(
        base._synthetic_log(ACCEPTED_EVR2_REL_ERROR, []),
        _dofmap_for_counts(nonhistorical_dofs),
        returncode=1,
        experiment_identity=_identity_drift(),
        mechanism_applicability=_applicability_pass(),
    )
    _require(
        result.get("ds_discriminator", {}).get("status") == "PASS",
        "nonhistorical valid topology was not accepted by the structural DS analyzer",
    )
    _require(
        result["status"] == "HOLD"
        and result["class"] == "FD_REFERENCE_EXPERIMENT_DRIFT",
        "analyzer applicability was incorrectly promoted to Issue46 experiment identity",
    )
    directional = result.get("directional", {})
    variables = directional.get("dof_map", {}).get("variables", {})
    _require(
        len(variables.get("n_e", [])) == nonhistorical_dofs,
        "nonhistorical valid electron topology was not analyzed structurally",
    )
    _require(
        len(variables.get(inv.LAMBDA_VARIABLE, [])) == 1,
        "scalar multiplier topology was not resolved structurally",
    )


def _check_wp3_evidence_decomposition() -> None:
    accepted_log = base._synthetic_log(ACCEPTED_EVR2_REL_ERROR, [])
    accepted = base.analyze_ds_runtime(
        accepted_log,
        _historical_evr2_dofmap(),
        returncode=1,
        experiment_identity=_identity_pass(),
        mechanism_applicability=_applicability_pass(),
    )
    _require(
        accepted["status"] == "PASS" and accepted["class"] == ACCEPTED_FINAL_CLASS,
        "accepted EVR2 vector no longer composes to the accepted final class",
    )
    _require(
        accepted.get("mechanism_evidence", {}).get("class")
        == "WP_QUANTIZATION_MECHANISM_CHARACTERIZED",
        "historical WP mechanism is not represented as an explicit evidence channel",
    )
    _require(
        accepted.get("ds_discriminator", {}).get("class")
        == "DS_REFERENCE_JACOBIAN_PASS",
        "DS Jacobian correctness is not represented as an independent evidence channel",
    )
    _require(
        accepted.get("termination", {}).get("class")
        == "EXPECTED_DIAGNOSTIC_NONCONVERGENCE",
        "accepted rc=1 DIVERGED_BREAKDOWN was not recognized as admissible diagnostic termination",
    )

    unresolved = base.analyze_ds_runtime(
        accepted_log,
        _historical_evr2_dofmap(),
        returncode=1,
        experiment_identity=_identity_pass(),
        mechanism_applicability=_applicability_hold(),
    )
    _require(
        unresolved["status"] == "HOLD"
        and unresolved["class"] == "FD_REFERENCE_MECHANISM_APPLICABILITY_HOLD",
        "DS success alone over-claimed the WP quantization mechanism",
    )
    _require(
        unresolved.get("ds_discriminator", {}).get("status") == "PASS",
        "mechanism applicability HOLD incorrectly erased independent DS evidence",
    )


def _check_wp3_termination_false_pass_controls() -> None:
    accepted_log = base._synthetic_log(ACCEPTED_EVR2_REL_ERROR, [])
    fatal_log = accepted_log + "Segmentation fault (core dumped)\n"
    fatal = base.analyze_ds_runtime(
        fatal_log,
        _historical_evr2_dofmap(),
        returncode=139,
        experiment_identity=_identity_pass(),
        mechanism_applicability=_applicability_pass(),
    )
    _require(
        fatal.get("termination", {}).get("class") == "FATAL_RUNTIME_FAILURE",
        "fatal runtime signature was not classified as fatal",
    )
    _require(fatal["status"] == "HOLD", "fatal runtime incorrectly produced final PASS")

    truncated_log = accepted_log.split("Linear solve did not converge", 1)[0]
    truncated = base.analyze_ds_runtime(
        truncated_log,
        _historical_evr2_dofmap(),
        returncode=0,
        experiment_identity=_identity_pass(),
        mechanism_applicability=_applicability_pass(),
    )
    _require(
        truncated["status"] == "HOLD"
        and truncated.get("ds_discriminator", {}).get("class")
        == "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
        "truncated threshold-matrix evidence was over-classified",
    )


def _check_wp3_provenance_separation() -> None:
    _require(
        not hasattr(base, "WP_OBSERVED_ATTENUATION"),
        "historical observed attenuation still leaks into production decision constants",
    )
    mechanism = base._historical_mechanism_evidence()
    reference = mechanism.get("reference_source", {})
    _require(
        reference.get("project") == "PETSc"
        and reference.get("version") == "3.25.2",
        "PETSc mechanism reference-source provenance is not explicit",
    )
    _require(
        mechanism.get("runtime_identity") == "OBSERVED_SEPARATELY",
        "reference-source provenance still masquerades as runtime identity",
    )


def _check_accepted_evr2_result_vector() -> None:
    result = base.analyze_ds_runtime(
        base._synthetic_log(ACCEPTED_EVR2_REL_ERROR, []),
        _historical_evr2_dofmap(),
        returncode=1,
        experiment_identity=_identity_pass(),
        mechanism_applicability=_applicability_pass(),
    )
    _require(result["status"] == "PASS", "accepted EVR2 vector no longer passes")
    _require(
        result["class"] == ACCEPTED_FINAL_CLASS,
        f"accepted EVR2 class drifted: {result['class']}",
    )
    metrics = result["directional"]["metrics"]
    _require(
        metrics["nonzero_thresholded_entry_count"] == 0,
        "accepted EVR2 zero-difference signature drifted",
    )
    _require(
        metrics["j_lambda_n"]["count"] == 0
        and metrics["j_n_lambda"]["count"] == 0,
        "accepted EVR2 directional zero signature drifted",
    )


def main() -> int:
    checks: tuple[tuple[str, Callable[[], None]], ...] = (
        ("canonical-owner-self-test", lambda: _require(
            base.self_test() == 0,
            "canonical Issue46 FD-reference self-test failed",
        )),
        ("accepted-and-state-explicit-predictor", _check_predictor),
        ("structural-zero-and-directions", _check_structural_zero_and_directions),
        ("dofmap-negative-controls", _check_dofmap_negative_controls),
        ("ds-structure-controls", _check_ds_structure_controls),
        ("runtime-topology-not-historical-literal", _check_runtime_topology_not_historical_literal),
        ("wp3-evidence-decomposition", _check_wp3_evidence_decomposition),
        ("wp3-termination-false-pass-controls", _check_wp3_termination_false_pass_controls),
        ("wp3-provenance-separation", _check_wp3_provenance_separation),
        ("accepted-evr2-result-vector", _check_accepted_evr2_result_vector),
    )
    try:
        for check_id, check in checks:
            check()
            print(f"ISSUE47_WP1_CHARACTERIZATION_CHECK: {check_id}=PASS")
    except Exception as exc:
        print(f"ISSUE47_WP1_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE47_WP1_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
