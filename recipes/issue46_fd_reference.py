"""Issue46 FD-reference policy composed from reusable QPX harness primitives.

This module owns Issue46 experiment constants and scientific composition only.
MOOSE/PETSc parsing, mutation, matrix ownership, floating-point representability,
and artifact freshness mechanics are delegated to general qpx_harness modules.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from qpx_harness import artifacts
from qpx_harness.moose import dofmap as dm
from qpx_harness.moose import log as moose_log
from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import fd_reference as fd
from qpx_harness.petsc import jacobian as jac
from qpx_harness.petsc import log as petsc_log
from qpx_harness.petsc import matrix as matrix
from qpx_harness.petsc import options as options

ISSUE = 46
TARGET = 1.0e16
HISTORICAL_EVR1_ELECTRON_DOF_COUNT = 2348
PETSC_REFERENCE_VERSION = "3.25.2"
FD_REFERENCE_TYPE = "ds"
GLOBAL_JACOBIAN_REL_TOL = 1.0e-6
LOCALIZATION_THRESHOLD = 1.0e-7
DS_ATTENUATION_TO_UNITY_TOL = 1.0e-8
ELECTRON_VARIABLE = "n_e"
POTENTIAL_VARIABLE = "potential_plasma"
LAMBDA_VARIABLE = "r45_inventory_lambda"
MAIN_VARIABLES = (ELECTRON_VARIABLE, POTENTIAL_VARIABLE, LAMBDA_VARIABLE)
SCALAR_VARIABLES = (LAMBDA_VARIABLE,)


class Issue46FDReferenceError(RuntimeError):
    pass


def predict_fd_step_quantization(*, vector_norm: float, component_value: float) -> dict[str, float]:
    try:
        return fd.predict_wp_ds_representability(
            vector_norm=vector_norm,
            component_value=component_value,
        )
    except fd.FDReferenceError as exc:
        raise Issue46FDReferenceError(str(exc)) from exc


def historical_evr1_prediction() -> dict[str, float]:
    vector_norm = math.sqrt(float(HISTORICAL_EVR1_ELECTRON_DOF_COUNT)) * abs(TARGET)
    return {
        "electron_dofs": float(HISTORICAL_EVR1_ELECTRON_DOF_COUNT),
        "electron_value": TARGET,
        "vector_norm_model": vector_norm,
        **predict_fd_step_quantization(vector_norm=vector_norm, component_value=TARGET),
    }


def historical_mechanism_evidence() -> dict[str, Any]:
    return {
        "status": "PASS",
        "class": "WP_QUANTIZATION_MECHANISM_CHARACTERIZED",
        "issue": ISSUE,
        "evr": 1,
        "evidence_level": "accepted-result-vector",
        "reference_source": {
            "project": "PETSc",
            "version": PETSC_REFERENCE_VERSION,
            "purpose": "WP/DS finite-difference step mechanism contract",
        },
        "runtime_identity": "OBSERVED_SEPARATELY",
    }


def _jacobian_analysis(text: str, *, relative_tolerance: float) -> dict[str, Any]:
    tests = jac.parse_comparisons(text)
    if not tests:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_EVIDENCE_INSUFFICIENT",
            "reason": "PETSc -snes_test_jacobian produced no parseable Jacobian comparison",
            "relative_tolerance": relative_tolerance,
            "tests": [],
        }
    nonfinite = [
        item for item in tests
        if not math.isfinite(item["relative_frobenius_error"])
        or not math.isfinite(item["absolute_frobenius_error"])
    ]
    finite_rel = [
        item["relative_frobenius_error"]
        for item in tests
        if math.isfinite(item["relative_frobenius_error"])
    ]
    worst = max(finite_rel) if finite_rel else math.inf
    if nonfinite or worst > relative_tolerance:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_MISMATCH",
            "reason": (
                "assembled-vs-finite-difference Jacobian relative Frobenius error exceeds "
                f"the declared tolerance {relative_tolerance:g} or is non-finite"
            ),
            "relative_tolerance": relative_tolerance,
            "worst_relative_frobenius_error": worst,
            "nonfinite": nonfinite,
            "tests": tests,
        }
    return {
        "status": "PASS",
        "class": "JACOBIAN_CORRECTNESS_PASS",
        "reason": "all observed PETSc Jacobian comparisons satisfy the declared relative tolerance",
        "relative_tolerance": relative_tolerance,
        "worst_relative_frobenius_error": worst,
        "nonfinite": [],
        "tests": tests,
    }


def _runtime_core_facts(log_text: str, *, returncode: int) -> dict[str, Any]:
    residual_blocks = moose_log.parse_variable_residual_norms(log_text)
    linear_rows = petsc_log.parse_linear_solve_terminations(log_text)
    nonlinear_rows = petsc_log.parse_nonlinear_solve_terminations(log_text)
    linear_reason = next((row["reason"] for row in linear_rows if not row["converged"]), None)
    nonlinear_reason = next((row["reason"] for row in nonlinear_rows if not row["converged"]), None)
    pc_failure_reason = petsc_log.parse_pc_failure_reason(log_text)
    nonfinite_residuals: list[dict[str, Any]] = []
    for index, block in enumerate(residual_blocks):
        for name, value in block.items():
            if not math.isfinite(value):
                nonfinite_residuals.append(
                    {"block": index, "variable": name, "value": repr(value)}
                )
    return {
        "returncode": returncode,
        "linear_reason": linear_reason,
        "nonlinear_reason": nonlinear_reason,
        "pc_failure_reason": pc_failure_reason,
        "variable_residuals": residual_blocks,
        "nonfinite_residuals": nonfinite_residuals,
    }


def termination_admissibility(log_text: str, *, returncode: int) -> dict[str, Any]:
    core = _runtime_core_facts(log_text, returncode=returncode)
    fatal = petsc_log.line_hits(
        log_text,
        (r"segmentation fault", r"core dumped", r"signal\s+11", r"fatal error", r"terminate called", r"\babort(?:ed)?\b"),
    )
    pc_failure = (
        core.get("pc_failure_reason")
        or core.get("linear_reason") in {"DIVERGED_PC_FAILED", "DIVERGED_PCSETUP_FAILED"}
        or bool(
            petsc_log.line_hits(
                log_text,
                (r"FACTOR_(?:NUMERIC|STRUCT)_ZEROPIVOT", r"PC failed due to", r"zero pivot", r"PCSetUp.*fail"),
            )
        )
    )
    nonfinite = bool(core.get("nonfinite_residuals")) or core.get("nonlinear_reason") == "DIVERGED_FUNCTION_NANORINF"
    if fatal or pc_failure or nonfinite:
        return {
            "status": "HOLD",
            "class": "FATAL_RUNTIME_FAILURE",
            "reason": "fatal, PC/factorization, or non-finite runtime evidence invalidates the Jacobian observation",
            "returncode": returncode,
            "core": core,
        }
    if returncode == 0:
        return {
            "status": "PASS",
            "class": "TERMINATION_SUCCESS",
            "reason": "runtime returned successfully with no fatal invalidation signature",
            "returncode": returncode,
            "core": core,
        }
    if core.get("linear_reason") == "DIVERGED_BREAKDOWN":
        return {
            "status": "PASS",
            "class": "EXPECTED_DIAGNOSTIC_NONCONVERGENCE",
            "reason": "nonzero process return is attributable to the predeclared diagnostic DIVERGED_BREAKDOWN path",
            "returncode": returncode,
            "core": core,
        }
    return {
        "status": "HOLD",
        "class": "TERMINATION_AMBIGUOUS",
        "reason": "nonzero process return lacks a predeclared admissible diagnostic termination signature",
        "returncode": returncode,
        "core": core,
    }


def runtime_mechanism_applicability(log_text: str) -> dict[str, Any]:
    version = petsc_log.parse_petsc_version(log_text)
    if version is None:
        return {
            "status": "HOLD",
            "class": "PETSC_WP_MECHANISM_APPLICABILITY_UNRESOLVED",
            "reason": "runtime PETSc version is not observable in the diagnostic log",
            "reference_version": PETSC_REFERENCE_VERSION,
            "runtime_version": "UNKNOWN",
        }
    if version != PETSC_REFERENCE_VERSION:
        return {
            "status": "HOLD",
            "class": "PETSC_WP_MECHANISM_APPLICABILITY_DRIFT",
            "reason": "runtime PETSc realization differs from the source realization used to establish the WP mechanism",
            "reference_version": PETSC_REFERENCE_VERSION,
            "runtime_version": version,
        }
    return {
        "status": "PASS",
        "class": "PETSC_WP_MECHANISM_APPLICABILITY_PASS",
        "reason": "runtime PETSc version matches the accepted WP/DS mechanism reference realization",
        "reference_version": PETSC_REFERENCE_VERSION,
        "runtime_version": version,
    }


def evidence_provenance_status(
    *,
    root: Path,
    case_dir: Path,
    input_path: Path,
    source_case: Path,
    input_sha_before: str,
    input_sha_after: str,
    log_path: Path,
    log_preexisting: bool,
    log_exists: bool,
    dofmap_path: Path,
    dofmap_preexisting: bool,
    dofmap_exists: bool,
    source_dofmaps_before: tuple[str, ...],
    source_dofmaps_after: tuple[str, ...],
) -> dict[str, Any]:
    checks = {
        "runner-owned-case": artifacts.is_direct_child(case_dir, root),
        "runner-owned-input": artifacts.is_direct_child(input_path, case_dir),
        "source-case-isolated": artifacts.paths_distinct(case_dir, source_case),
        "input-identity-stable": artifacts.identity_stable(input_sha_before, input_sha_after),
        "current-run-log": artifacts.current_run_artifact(
            log_path,
            expected_parent=root,
            existed_before=log_preexisting,
            exists_after=log_exists,
        ),
        "current-run-dofmap": artifacts.current_run_artifact(
            dofmap_path,
            expected_parent=case_dir,
            existed_before=dofmap_preexisting,
            exists_after=dofmap_exists,
        ),
        "canonical-source-output-unchanged": artifacts.snapshot_unchanged(
            source_dofmaps_before, source_dofmaps_after
        ),
    }
    summary = artifacts.summarize_checks(checks)
    status = "PASS" if summary["ok"] else "HOLD"
    return {
        "status": status,
        "class": "EVIDENCE_PROVENANCE_PASS" if status == "PASS" else "EVIDENCE_PROVENANCE_HOLD",
        "reason": (
            "runtime log, DOFMap, and input identity are bound to the fresh runner-owned copied case"
            if status == "PASS"
            else "runtime evidence is stale, unowned, identity-drifted, or touched the canonical source case"
        ),
        "checks": [
            {"id": item["id"], "status": "PASS" if item["ok"] else "FAIL"}
            for item in summary["checks"]
        ],
        "blockers": list(summary["blockers"]),
        "input_sha_before": input_sha_before,
        "input_sha_after": input_sha_after,
        "source_dofmaps_before": list(source_dofmaps_before),
        "source_dofmaps_after": list(source_dofmaps_after),
    }


def directional_localization(log_text: str, dofmap_text: str) -> dict[str, Any]:
    try:
        dof_map = dm.parse_dof_map_text(
            dofmap_text,
            expected_variables=MAIN_VARIABLES,
            scalar_variables=SCALAR_VARIABLES,
        )
        difference = matrix.parse_threshold_difference_matrix(log_text)
        nonzero = matrix.finite_nonzero_entries(difference)
        localized = matrix.summarize_by_owner(nonzero, dof_map["owner_by_dof"])
    except (dm.DofMapError, matrix.MatrixParseError) as exc:
        raise Issue46FDReferenceError(str(exc)) from exc

    category_energy = {"constraint_lm": 0.0, "electron_potential": 0.0, "other": 0.0}
    total_energy = 0.0
    for block in localized["blocks"].values():
        energy = float(block["sum_squared_difference"])
        total_energy += energy
        row_var = block["row_variable"]
        col_var = block["col_variable"]
        if row_var == LAMBDA_VARIABLE or col_var == LAMBDA_VARIABLE:
            category = "constraint_lm"
        elif {row_var, col_var} == {ELECTRON_VARIABLE, POTENTIAL_VARIABLE}:
            category = "electron_potential"
        else:
            category = "other"
        category_energy[category] += energy
    localized["category_energy_fraction"] = {
        name: (energy / total_energy if total_energy > 0.0 else 0.0)
        for name, energy in category_energy.items()
    }

    j_lambda_n = localized["blocks"].get(f"{LAMBDA_VARIABLE}->{ELECTRON_VARIABLE}", {})
    j_n_lambda = localized["blocks"].get(f"{ELECTRON_VARIABLE}->{LAMBDA_VARIABLE}", {})
    return {
        "dof_map": {
            "ndof": dof_map["ndof"],
            "variables": dof_map["variables"],
        },
        "difference": nonzero,
        "localization": localized,
        "metrics": {
            "structural_entry_count": nonzero["structural_entry_count"],
            "nonzero_thresholded_entry_count": localized.get("mapped_entry_count", 0),
            "j_lambda_n": {
                "count": int(j_lambda_n.get("count", 0)),
                "l2_difference": float(j_lambda_n.get("l2_difference", 0.0)),
                "max_abs_difference": float(j_lambda_n.get("max_abs_difference", 0.0)),
            },
            "j_n_lambda": {
                "count": int(j_n_lambda.get("count", 0)),
                "l2_difference": float(j_n_lambda.get("l2_difference", 0.0)),
                "max_abs_difference": float(j_n_lambda.get("max_abs_difference", 0.0)),
            },
        },
    }


def instrument_ds_reference(baseline_text: str) -> tuple[str, dict[str, Any]]:
    pairs = options.get_name_value_pairs(baseline_text)
    if any(name == "-mat_fd_type" for name, _ in pairs):
        raise Issue46FDReferenceError("baseline already specifies -mat_fd_type")
    out = options.upsert_name_value(baseline_text, "-mat_fd_type", FD_REFERENCE_TYPE)
    return out, {
        "mat_fd_type": FD_REFERENCE_TYPE,
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "scaling_policy_changed": False,
        "finite_difference_observation_changed": True,
    }


def remove_fd_type_pair(text: str) -> str:
    pairs = options.get_name_value_pairs(text)
    fd_pairs = [(name, value) for name, value in pairs if name == "-mat_fd_type"]
    if fd_pairs != [("-mat_fd_type", FD_REFERENCE_TYPE)]:
        raise Issue46FDReferenceError(
            f"expected exactly -mat_fd_type {FD_REFERENCE_TYPE}, got {fd_pairs}"
        )
    return options.set_name_value_pairs(
        text,
        [(name, value) for name, value in pairs if name != "-mat_fd_type"],
    )


def mask_petsc_pair_lines(text: str) -> str:
    out = mp.upsert_parameter(text, "Executioner", "petsc_options_iname", "'<PETSC_INAMES>'")
    return mp.upsert_parameter(out, "Executioner", "petsc_options_value", "'<PETSC_VALUES>'")


def analyze_ds_runtime(
    log_text: str,
    dofmap_text: str,
    *,
    returncode: int,
    experiment_identity: dict[str, Any] | None = None,
    mechanism_applicability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    jacobian = _jacobian_analysis(log_text, relative_tolerance=GLOBAL_JACOBIAN_REL_TOL)
    mechanism = historical_mechanism_evidence()
    identity = experiment_identity or {
        "status": "HOLD",
        "class": "ISSUE46_EXPERIMENT_IDENTITY_UNRESOLVED",
        "reason": "analyzer applicability does not establish Issue46 experiment identity",
    }
    applicability = mechanism_applicability or runtime_mechanism_applicability(log_text)
    termination = termination_admissibility(log_text, returncode=returncode)

    try:
        directional = directional_localization(log_text, dofmap_text)
    except Issue46FDReferenceError as exc:
        ds = {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": str(exc),
        }
        return {
            **ds,
            "returncode": returncode,
            "jacobian": jacobian,
            "mechanism_evidence": mechanism,
            "mechanism_applicability": applicability,
            "experiment_identity": identity,
            "termination": termination,
            "ds_discriminator": ds,
            "prediction": historical_evr1_prediction(),
        }

    variables = directional["dof_map"]["variables"]
    n_count = len(variables.get(ELECTRON_VARIABLE, []))
    potential_count = len(variables.get(POTENTIAL_VARIABLE, []))
    lambda_count = len(variables.get(LAMBDA_VARIABLE, []))
    metrics = directional["metrics"]
    section_complete = matrix.has_closing_runtime_boundary(log_text)

    if n_count <= 0 or potential_count <= 0 or lambda_count != 1:
        ds = {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": "runtime DOF ownership is structurally incomplete for the electron, potential, or scalar-multiplier roles",
        }
    elif termination["status"] != "PASS":
        ds = {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": f"runtime termination is not admissible: {termination['class']}",
        }
    elif not section_complete:
        ds = {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": "thresholded Jacobian-difference evidence is truncated or lacks a closing runtime boundary",
        }
    elif jacobian.get("class") == "JACOBIAN_CORRECTNESS_PASS" and metrics["nonzero_thresholded_entry_count"] == 0:
        ds = {
            "status": "PASS",
            "class": "DS_REFERENCE_JACOBIAN_PASS",
            "reason": "the assembled Jacobian passes under the DS finite-difference reference with structurally valid role ownership and no nonzero thresholded difference entries",
        }
    elif jacobian.get("class") == "JACOBIAN_MISMATCH" and metrics["j_lambda_n"]["count"] > 0:
        ds = {
            "status": "HOLD",
            "class": "FD_REFERENCE_MISMATCH_PERSISTS",
            "reason": "J_lambda,n mismatch persists under the DS finite-difference reference",
        }
    else:
        ds = {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": "DS finite-difference evidence does not meet a predeclared conclusive branch",
        }

    if ds["class"] == "FD_REFERENCE_MISMATCH_PERSISTS":
        decision = dict(ds)
    elif ds["status"] != "PASS":
        decision = {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": ds["reason"],
        }
    elif identity.get("status") != "PASS":
        decision = {
            "status": "HOLD",
            "class": "FD_REFERENCE_EXPERIMENT_DRIFT",
            "reason": identity.get("reason", "Issue46 experiment identity is not established"),
        }
    elif mechanism.get("status") != "PASS":
        decision = {
            "status": "HOLD",
            "class": "FD_REFERENCE_MECHANISM_EVIDENCE_HOLD",
            "reason": mechanism.get("reason", "historical WP mechanism evidence is unavailable"),
        }
    elif applicability.get("status") != "PASS":
        decision = {
            "status": "HOLD",
            "class": "FD_REFERENCE_MECHANISM_APPLICABILITY_HOLD",
            "reason": applicability.get("reason", "runtime WP mechanism applicability is unresolved"),
        }
    else:
        decision = {
            "status": "PASS",
            "class": "FD_REFERENCE_QUANTIZATION_CONFIRMED",
            "reason": "the accepted WP quantization mechanism, Issue46 experiment identity, admissible runtime termination, and independent DS Jacobian discriminator all pass",
        }

    return {
        **decision,
        "returncode": returncode,
        "jacobian": jacobian,
        "directional": directional,
        "mechanism_evidence": mechanism,
        "mechanism_applicability": applicability,
        "experiment_identity": identity,
        "termination": termination,
        "ds_discriminator": ds,
        "prediction": historical_evr1_prediction(),
    }
