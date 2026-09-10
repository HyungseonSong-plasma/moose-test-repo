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

from physics_harness.adapters.moose import dofmap as dm
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.input import MooseInput
from physics_harness.adapters.moose import petsc_options
from physics_harness.adapters.petsc import fd_reference as fd
from physics_harness.adapters.petsc import matrix as petsc_matrix
from experiments.historical_recipe_support import issue45_first_linear as first_linear
from experiments.historical_recipe_support import issue45_inventory_constraint as inventory
from experiments.historical_recipe_support import issue46_fd_reference as base
from experiments.historical_recipe_support import issue46_jacobian_localization as loc


ACCEPTED_EVR1_ELECTRON_DOF_COUNT = 2348
ACCEPTED_EVR1_OBSERVED_ATTENUATION = 0.96406286
ACCEPTED_EVR2_REL_ERROR = 5.35565e-11
ACCEPTED_FINAL_CLASS = "FD_REFERENCE_QUANTIZATION_CONFIRMED"
ACCEPTED_WP_PREDICTED_ATTENUATION = 0.9640628864075022


class CharacterizationFailure(AssertionError):
    pass


class HistoricalIssue46LocalizationError(RuntimeError):
    """Test-only compatibility error for the retired Issue46 parser facade."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CharacterizationFailure(message)


def _parse_dof_map_text(text: str) -> dict[str, object]:
    """Preserve the retired Issue46 DOFMap wrapper contract over the canonical parser."""
    try:
        return dm.parse_dof_map_text(
            text,
            expected_variables=base.MAIN_VARIABLES,
            scalar_variables=base.SCALAR_VARIABLES,
        )
    except dm.DofMapError as exc:
        raise HistoricalIssue46LocalizationError(str(exc)) from exc


def _expect_dofmap_rejection(text: str, expected_fragment: str) -> None:
    try:
        _parse_dof_map_text(text)
    except HistoricalIssue46LocalizationError as exc:
        _require(
            expected_fragment in str(exc),
            f"DOFMap rejection mismatch: expected {expected_fragment!r}, got {exc!s}",
        )
        return
    raise CharacterizationFailure(
        f"DOFMap mutation unexpectedly passed: expected {expected_fragment!r}"
    )


def _historical_issue45_constrained_input(
    macro_avg: float = inventory.DEFAULT_MACRO_ELECTRON_AVG,
) -> str:
    """Preserve the accepted pre-retirement synthetic constrained fixture."""
    boundaries = " ".join(sorted(inventory.EXPECTED_DRIFT_BOUNDARIES))
    return f"""[Variables]
  [n_e]
    type = MooseVariableFVReal
  []
  [potential_plasma]
    type = MooseVariableFVReal
  []
  [{inventory.LAMBDA_VARIABLE}]
    type = MooseVariableScalar
  []
[]
[FVKernels]
  [diffusion]
    type = FVDiffusion
    variable = n_e
  []
  [drift]
    type = {inventory.DRIFT_TYPE}
    variable = n_e
    boundaries_to_avoid = '{boundaries}'
  []
  [phi]
    type = FVDiffusion
    variable = potential_plasma
  []
  [inventory_constraint]
    type = {inventory.CONSTRAINT_TYPE}
    variable = n_e
    lambda = {inventory.LAMBDA_VARIABLE}
    phi0 = {inventory.MACRO_AVG_POSTPROCESSOR}
    block = plasma
  []
[]
[FVBCs]
  [g0]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_metal
    value = 0
  []
  [g1]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_electrode
    value = 0
  []
  [g2]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_right
    value = 0
  []
  [g3]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = inlet
    value = 0
  []
  [g4]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = outlet
    value = 0
  []
[]
[Postprocessors]
  [{inventory.MACRO_AVG_POSTPROCESSOR}]
    type = ConstantPostprocessor
    value = {macro_avg:.17g}
  []
[]
[Executioner]
  type = Steady
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]
[Outputs]
  [out]
    type = CSV
    execute_on = FINAL
  []
  [console]
    type = Console
    execute_on = FINAL
    all_variable_norms = true
  []
[]
[Debug]
  show_var_residual_norms = true
[]
"""


def _fixed_c0_fixture() -> str:
    """Build the accepted pre-retirement Issue46 synthetic C0 fixture."""
    return mp.upsert_parameter(
        _historical_issue45_constrained_input(base.TARGET),
        "Variables/n_e",
        "initial_condition",
        f"{base.TARGET:.17g}",
    )


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
                    "name": base.LAMBDA_VARIABLE,
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


def _synthetic_log(relative_error: float, rows: list[str]) -> str:
    """Preserve the pre-retirement Issue46 synthetic runtime-log fixture."""
    return (
        "  ---------- Testing Jacobian -------------\n"
        f"  ||J - Jfd||_F/||J||_F = {relative_error:.12e}, "
        "||J - Jfd||_F = 1e-6\n"
        f"  Hand-coded minus finite-difference Jacobian with tolerance "
        f"{base.LOCALIZATION_THRESHOLD:.12e} ----------\n"
        "Mat Object: 1 MPI process\n  type: seqaij\n"
        + "\n".join(rows)
        + "\nLinear solve did not converge due to DIVERGED_BREAKDOWN iterations 30\n"
    )


def _audit_ds_reference_structure(
    baseline_text: str, ds_text: str
) -> dict[str, object]:
    """Preserve the retired facade's DS observation-only structural oracle."""
    checks: list[dict[str, object]] = []

    def add(name: str, ok: bool, observed: object, required: object) -> None:
        checks.append(
            {
                "id": name,
                "status": "PASS" if ok else "FAIL",
                "observed": observed,
                "required": required,
            }
        )

    try:
        baseline_pairs = petsc_options.get_name_value_pairs(baseline_text)
        ds_pairs = petsc_options.get_name_value_pairs(ds_text)
    except petsc_options.PetscOptionsError as exc:
        return {
            "status": "HOLD",
            "class": "FD_REFERENCE_DS_STRUCTURE_FAIL",
            "checks": [],
            "blockers": [
                {
                    "id": "petsc-name-value-structure",
                    "status": "FAIL",
                    "observed": str(exc),
                    "required": "valid PETSc name/value pairs",
                }
            ],
            "prediction": base.historical_evr1_prediction(),
            "mechanism_evidence": base.historical_mechanism_evidence(),
            "closure": {},
        }

    expected_pairs = baseline_pairs + [("-mat_fd_type", base.FD_REFERENCE_TYPE)]
    add("ds-petsc-pair-exact", ds_pairs == expected_pairs, ds_pairs, expected_pairs)
    add(
        "petsc-flags-preserved",
        petsc_options.get_flags(ds_text) == petsc_options.get_flags(baseline_text),
        petsc_options.get_flags(ds_text),
        petsc_options.get_flags(baseline_text),
    )

    restored: str | None = None
    try:
        restored = base.remove_fd_type_pair(ds_text)
        restored_pairs = petsc_options.get_name_value_pairs(restored)
        semantic_pair_restore = restored_pairs == baseline_pairs
        masked_byte_equal = base.mask_petsc_pair_lines(
            restored
        ) == base.mask_petsc_pair_lines(baseline_text)
    except (
        base.Issue46FDReferenceError,
        mp.MooseParameterError,
        petsc_options.PetscOptionsError,
    ):
        semantic_pair_restore = False
        masked_byte_equal = False
    add(
        "observation-only-petsc-pair-restore",
        semantic_pair_restore,
        semantic_pair_restore,
        True,
    )
    add(
        "observation-only-masked-byte-guard",
        masked_byte_equal,
        masked_byte_equal,
        True,
    )

    canonical_for_closure = restored if restored is not None else baseline_text
    closure = inventory.audit_constrained_quasisteady_structure(
        canonical_for_closure, expected_macro_avg=base.TARGET
    )
    add(
        "c0-closure-preserved",
        closure["status"] == "PASS",
        closure["status"],
        "PASS",
    )

    initial = mp.unquote(
        mp.get_parameter(canonical_for_closure, "Variables/n_e", "initial_condition")
    )
    try:
        initial_value = float(initial)
    except (TypeError, ValueError):
        initial_value = math.nan
    add("c0-electron-initial-state", initial_value == base.TARGET, initial_value, base.TARGET)

    prediction = base.historical_evr1_prediction()
    mechanism = base.historical_mechanism_evidence()
    add(
        "historical-wp-mechanism-characterized",
        mechanism["status"] == "PASS",
        mechanism["class"],
        "WP_QUANTIZATION_MECHANISM_CHARACTERIZED",
    )
    add(
        "ds-electron-step-representable",
        abs(prediction["ds_predicted_attenuation"] - 1.0)
        <= base.DS_ATTENUATION_TO_UNITY_TOL,
        prediction["ds_predicted_attenuation"],
        f"within {base.DS_ATTENUATION_TO_UNITY_TOL:g} of 1",
    )

    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": (
            "FD_REFERENCE_DS_STRUCTURE_PASS"
            if not blockers
            else "FD_REFERENCE_DS_STRUCTURE_FAIL"
        ),
        "checks": checks,
        "blockers": blockers,
        "prediction": prediction,
        "mechanism_evidence": mechanism,
        "closure": closure,
    }


def _check_fd_reference_option_mutation() -> None:
    """Preserve the retired facade's malformed FD-option negative control."""
    fixture = _fixed_c0_fixture()
    baseline, ds_text = _baseline_and_ds(fixture)
    bad = ds_text.replace("-mat_fd_type", "-mat_fd_type_bad", 1)
    _require(
        _audit_ds_reference_structure(baseline, bad)["status"] != "PASS",
        "FD-reference option mutation was accepted",
    )


def _check_evidence_provenance_controls() -> None:
    """Preserve the retired facade's fresh/stale evidence provenance controls."""
    provenance_root = Path("/tmp/issue46-evidence")
    provenance_case = provenance_root / "c0_ds_reference"
    provenance_input = provenance_case / "input.i"
    provenance_log = provenance_root / "p3_c0_ds_reference.log"
    provenance_dofmap = provenance_case / f"{loc.DOFMAP_FILE_BASE}.json"
    common = {
        "root": provenance_root,
        "case_dir": provenance_case,
        "input_path": provenance_input,
        "source_case": Path("/tmp/issue46-source-case"),
        "input_sha_before": "abc",
        "input_sha_after": "abc",
        "log_path": provenance_log,
        "log_exists": True,
        "dofmap_path": provenance_dofmap,
        "dofmap_preexisting": False,
        "dofmap_exists": True,
        "source_dofmaps_before": (),
        "source_dofmaps_after": (),
    }
    fresh = base.evidence_provenance_status(log_preexisting=False, **common)
    _require(
        fresh["class"] == "EVIDENCE_PROVENANCE_PASS",
        "fresh runner-owned evidence provenance was rejected",
    )
    stale = base.evidence_provenance_status(log_preexisting=True, **common)
    _require(
        stale["class"] == "EVIDENCE_PROVENANCE_HOLD",
        "stale pre-existing runtime log was accepted",
    )


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
    expected_wp = math.sqrt(1.0 + vector_norm) * fd.SQRT_MACHINE_EPSILON
    expected_ds = component_value * fd.SQRT_MACHINE_EPSILON
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
    filtered = petsc_matrix.finite_nonzero_entries(raw)
    _require(filtered["structural_entry_count"] == 2, "structural count drifted")
    _require(
        filtered["nonzero_thresholded_entry_count"] == 1,
        "explicit structural zero was counted as a nonzero mismatch",
    )

    dofmap = _dofmap_for_counts(2)
    j_lambda_n = base.directional_localization(
        _synthetic_log(
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
        _synthetic_log(
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
                    "name": base.LAMBDA_VARIABLE,
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
                    "name": base.LAMBDA_VARIABLE,
                    "subdomains": [{"id": 1, "dofs": []}],
                },
            ],
        }
    )
    _expect_dofmap_rejection(unmapped, "cannot resolve scalar DOFs")


def _check_ds_structure_controls() -> None:
    fixture = _fixed_c0_fixture()
    baseline, ds_text = _baseline_and_ds(fixture)

    accepted = _audit_ds_reference_structure(baseline, ds_text)
    _require(
        accepted["status"] == "PASS",
        "accepted DS-only observation mutation no longer passes",
    )

    missing_c0 = _remove_parameter_line(
        fixture, "Variables/n_e", "initial_condition"
    )
    missing_baseline, missing_ds = _baseline_and_ds(missing_c0)
    missing_report = _audit_ds_reference_structure(
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

    material_mutation = petsc_options.upsert_name_value(ds_text, "-pc_type", "jacobi")
    material_report = _audit_ds_reference_structure(
        baseline, material_mutation
    )
    _require(
        material_report["status"] == "HOLD",
        "material PETSc option mutation unexpectedly passed",
    )


def _check_runtime_topology_not_historical_literal() -> None:
    nonhistorical_dofs = 3
    result = base.analyze_ds_runtime(
        _synthetic_log(ACCEPTED_EVR2_REL_ERROR, []),
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
        len(variables.get(base.LAMBDA_VARIABLE, [])) == 1,
        "scalar multiplier topology was not resolved structurally",
    )


def _check_wp3_evidence_decomposition() -> None:
    accepted_log = _synthetic_log(ACCEPTED_EVR2_REL_ERROR, [])
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
    accepted_log = _synthetic_log(ACCEPTED_EVR2_REL_ERROR, [])
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
    mechanism = base.historical_mechanism_evidence()
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
        _synthetic_log(ACCEPTED_EVR2_REL_ERROR, []),
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


def _historical_fd_reference_self_test() -> int:
    """Run the retired facade P0 contract against preserved/current owners."""
    try:
        _check_predictor()
        _check_structural_zero_and_directions()
        _check_ds_structure_controls()
        _check_fd_reference_option_mutation()
        _check_wp3_termination_false_pass_controls()
        _check_wp3_provenance_separation()
        _check_evidence_provenance_controls()
    except Exception as exc:
        print(f"ISSUE46_FD_REFERENCE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE46_FD_REFERENCE_SELFTEST: PASS")
    return 0


def main() -> int:
    checks: tuple[tuple[str, Callable[[], None]], ...] = (
        ("canonical-owner-self-test", lambda: _require(
            _historical_fd_reference_self_test() == 0,
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
