"""Issue46 PETSc finite-difference reference audit.

This module repairs the EVR1 difference-count semantics and owns the bounded
EVR2 observation-only discriminator. The physical C0 problem, nonlinear
system, scaling policy, and solver realization are preserved. The only EVR2
change is PETSc's Jacobian-test reference differencing algorithm: default WP is
replaced by DS so the O(1e16) electron-density perturbation is representable in
double precision.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from . import augmented_jacobian_localization as loc
from . import electron_inventory_nullspace as inv
from . import evidence
from . import fast_plasma_coupling_diagnostic as coupling_diag
from . import fast_plasma_relaxation_v2 as v2
from . import petsc_first_linear_diagnostic as first_linear
from .moose_input import MooseInput, MooseInputError
from .runtime import run_qpx

ISSUE = 46
TARGET = inv.C0_TARGET
ACCEPTED_EVR1_ELECTRON_DOF_COUNT = 2348
FD_REFERENCE_TYPE = "ds"
GLOBAL_JACOBIAN_REL_TOL = first_linear.JACOBIAN_REL_TOL
LOCALIZATION_THRESHOLD = loc.LOCALIZATION_THRESHOLD
SQRT_MACHINE_EPSILON = math.sqrt(sys.float_info.epsilon)
WP_OBSERVED_ATTENUATION = 0.96406286
WP_ATTENUATION_MATCH_TOL = 1.0e-6
DS_ATTENUATION_TO_UNITY_TOL = 1.0e-8


class JacobianFDReferenceAuditError(RuntimeError):
    pass


def _issue46_synthetic_constrained_input(macro_avg: float = TARGET) -> str:
    """Build the Issue46 synthetic C0 fixture without mutating Issue45 ownership."""
    text = inv._synthetic_constrained_input(macro_avg)
    return inv._set_or_insert_parameter(
        text,
        "Variables/n_e",
        "initial_condition",
        f"{TARGET:.17g}",
    )


def predict_fd_step_quantization(
    *,
    electron_dofs: int = ACCEPTED_EVR1_ELECTRON_DOF_COUNT,
    electron_value: float = TARGET,
) -> dict[str, float]:
    if electron_dofs <= 0 or not math.isfinite(electron_value) or electron_value == 0.0:
        raise JacobianFDReferenceAuditError("invalid electron state for FD-step prediction")
    # Accepted C0 initial state: all n_e DOFs are 1e16; potential and scalar LM
    # initialize at zero, so the electron field dominates the global 2-norm.
    unorm = math.sqrt(float(electron_dofs)) * abs(electron_value)
    wp_requested = math.sqrt(1.0 + unorm) * SQRT_MACHINE_EPSILON
    wp_representable = (electron_value + wp_requested) - electron_value
    wp_attenuation = wp_representable / wp_requested

    # PETSc DS: dx = x_i * epsilon for this positive nonzero electron DOF.
    ds_requested = electron_value * SQRT_MACHINE_EPSILON
    ds_representable = (electron_value + ds_requested) - electron_value
    ds_attenuation = ds_representable / ds_requested
    return {
        "electron_dofs": float(electron_dofs),
        "electron_value": electron_value,
        "vector_norm_model": unorm,
        "sqrt_machine_epsilon": SQRT_MACHINE_EPSILON,
        "wp_requested_dx": wp_requested,
        "wp_representable_dx": wp_representable,
        "wp_predicted_attenuation": wp_attenuation,
        "ds_requested_dx": ds_requested,
        "ds_representable_dx": ds_representable,
        "ds_predicted_attenuation": ds_attenuation,
    }


def nonzero_threshold_difference(difference: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    structural_count = 0
    for entry in difference.get("entries", []):
        structural_count += 1
        try:
            value = float(entry["value"])
        except (KeyError, TypeError, ValueError):
            value = math.nan
        if not math.isfinite(value) or value != 0.0:
            entries.append({**entry, "value": value})
    return {
        "threshold": difference.get("threshold"),
        "entries": entries,
        "section_observed": difference.get("section_observed", False),
        "structural_entry_count": structural_count,
        "nonzero_thresholded_entry_count": sum(
            1
            for entry in entries
            if math.isfinite(float(entry.get("value", math.nan)))
        ),
    }


def directional_localization(log_text: str, dofmap_text: str) -> dict[str, Any]:
    try:
        dof_map = loc.parse_dof_map_text(dofmap_text)
        difference = loc.parse_threshold_difference_matrix(log_text)
        nonzero = nonzero_threshold_difference(difference)
        localized = loc.localize_difference_entries(nonzero, dof_map)
    except loc.AugmentedJacobianLocalizationError as exc:
        raise JacobianFDReferenceAuditError(str(exc)) from exc

    lm = inv.LAMBDA_VARIABLE
    j_lambda_n = localized["blocks"].get(f"{lm}->n_e", {})
    j_n_lambda = localized["blocks"].get(f"n_e->{lm}", {})
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
    pairs = loc._petsc_name_value_pairs(baseline_text)
    if any(name == "-mat_fd_type" for name, _ in pairs):
        raise JacobianFDReferenceAuditError("baseline already specifies -mat_fd_type")
    out = loc._upsert_petsc_value(baseline_text, "-mat_fd_type", FD_REFERENCE_TYPE)
    MooseInput(out)
    return out, {
        "mat_fd_type": FD_REFERENCE_TYPE,
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "scaling_policy_changed": False,
        "finite_difference_observation_changed": True,
    }


def _remove_fd_type_pair(text: str) -> str:
    pairs = loc._petsc_name_value_pairs(text)
    fd_pairs = [(name, value) for name, value in pairs if name == "-mat_fd_type"]
    if fd_pairs != [("-mat_fd_type", FD_REFERENCE_TYPE)]:
        raise JacobianFDReferenceAuditError(
            f"expected exactly -mat_fd_type {FD_REFERENCE_TYPE}, got {fd_pairs}"
        )
    filtered = [(name, value) for name, value in pairs if name != "-mat_fd_type"]
    return loc._set_petsc_name_value_pairs(text, filtered)


def _mask_petsc_pair_lines(text: str) -> str:
    """Mask only PETSc name/value pair serialization for byte-equivalence checks."""
    out = inv._set_or_insert_parameter(
        text, "Executioner", "petsc_options_iname", "'<PETSC_INAMES>'"
    )
    return inv._set_or_insert_parameter(
        out, "Executioner", "petsc_options_value", "'<PETSC_VALUES>'"
    )


def audit_ds_reference_structure(
    baseline_text: str, ds_text: str
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, observed: Any, required: Any) -> None:
        checks.append(
            {
                "id": name,
                "status": "PASS" if ok else "FAIL",
                "observed": observed,
                "required": required,
            }
        )

    baseline_pairs = loc._petsc_name_value_pairs(baseline_text)
    ds_pairs = loc._petsc_name_value_pairs(ds_text)
    expected_pairs = baseline_pairs + [("-mat_fd_type", FD_REFERENCE_TYPE)]
    add("ds-petsc-pair-exact", ds_pairs == expected_pairs, ds_pairs, expected_pairs)
    add(
        "petsc-flags-preserved",
        first_linear._petsc_options(ds_text) == first_linear._petsc_options(baseline_text),
        first_linear._petsc_options(ds_text),
        first_linear._petsc_options(baseline_text),
    )

    restored: str | None = None
    try:
        restored = _remove_fd_type_pair(ds_text)
        restored_pairs = loc._petsc_name_value_pairs(restored)
        semantic_pair_restore = restored_pairs == baseline_pairs
        masked_byte_equal = _mask_petsc_pair_lines(restored) == _mask_petsc_pair_lines(
            baseline_text
        )
    except (JacobianFDReferenceAuditError, inv.ElectronInventoryNullspaceError):
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

    # The #45 closure audit owns the accepted physics/solver contract. Apply it
    # to the canonical C0 restored after removing the observation-only FD option;
    # applying it directly to the instrumented input would conflate the
    # observation layer with the accepted numerical realization.
    canonical_for_closure = restored if restored is not None else baseline_text
    closure = inv.audit_constrained_quasisteady_structure(
        canonical_for_closure, expected_macro_avg=TARGET
    )
    add("c0-closure-preserved", closure["status"] == "PASS", closure["status"], "PASS")

    initial = inv._unquote(
        inv._parameter_value(canonical_for_closure, "Variables/n_e", "initial_condition")
    )
    try:
        initial_value = float(initial)
    except (TypeError, ValueError):
        initial_value = math.nan
    add("c0-electron-initial-state", initial_value == TARGET, initial_value, TARGET)

    prediction = predict_fd_step_quantization()
    add(
        "wp-mechanism-reproduces-evr1",
        abs(prediction["wp_predicted_attenuation"] - WP_OBSERVED_ATTENUATION)
        <= WP_ATTENUATION_MATCH_TOL,
        prediction["wp_predicted_attenuation"],
        f"within {WP_ATTENUATION_MATCH_TOL:g} of {WP_OBSERVED_ATTENUATION}",
    )
    add(
        "ds-electron-step-representable",
        abs(prediction["ds_predicted_attenuation"] - 1.0)
        <= DS_ATTENUATION_TO_UNITY_TOL,
        prediction["ds_predicted_attenuation"],
        f"within {DS_ATTENUATION_TO_UNITY_TOL:g} of 1",
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
        "closure": closure,
    }


def analyze_ds_runtime(
    log_text: str, dofmap_text: str, *, returncode: int
) -> dict[str, Any]:
    jacobian = coupling_diag.analyze_jacobian_text(
        log_text, relative_tolerance=GLOBAL_JACOBIAN_REL_TOL
    )
    try:
        directional = directional_localization(log_text, dofmap_text)
    except JacobianFDReferenceAuditError as exc:
        return {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": str(exc),
            "returncode": returncode,
            "jacobian": jacobian,
        }

    variables = directional["dof_map"]["variables"]
    n_count = len(variables.get("n_e", []))
    lambda_count = len(variables.get(inv.LAMBDA_VARIABLE, []))
    metrics = directional["metrics"]
    if n_count != ACCEPTED_EVR1_ELECTRON_DOF_COUNT or lambda_count != 1:
        decision = {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": "runtime DOF ownership no longer matches the accepted EVR1 C0 topology",
        }
    elif (
        jacobian.get("class") == "JACOBIAN_CORRECTNESS_PASS"
        and metrics["nonzero_thresholded_entry_count"] == 0
    ):
        decision = {
            "status": "PASS",
            "class": "FD_REFERENCE_QUANTIZATION_CONFIRMED",
            "reason": (
                "the exact C0 assembled Jacobian passes when only the PETSc FD "
                "reference changes from WP to DS, with no nonzero thresholded "
                "difference entries"
            ),
        }
    elif (
        jacobian.get("class") == "JACOBIAN_MISMATCH"
        and metrics["j_lambda_n"]["count"] > 0
    ):
        decision = {
            "status": "HOLD",
            "class": "FD_REFERENCE_MISMATCH_PERSISTS",
            "reason": "J_lambda,n mismatch persists under the DS finite-difference reference",
        }
    else:
        decision = {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": "DS finite-difference evidence does not meet a predeclared conclusive branch",
        }
    return {
        **decision,
        "returncode": returncode,
        "jacobian": jacobian,
        "directional": directional,
        "prediction": predict_fd_step_quantization(),
    }


def _synthetic_dofmap() -> str:
    return json.dumps(
        {
            "ndof": 5,
            "vars": [
                {"name": "n_e", "subdomains": [{"id": 1, "dofs": [0, 1]}]},
                {"name": "potential_plasma", "subdomains": [{"id": 1, "dofs": [2, 3]}]},
                {
                    "name": inv.LAMBDA_VARIABLE,
                    "subdomains": [{"id": 1, "dofs": []}],
                },
            ],
        }
    )


def _synthetic_log(relative_error: float, rows: list[str]) -> str:
    return (
        "  ---------- Testing Jacobian -------------\n"
        f"  ||J - Jfd||_F/||J||_F = {relative_error:.12e}, "
        "||J - Jfd||_F = 1e-6\n"
        f"  Hand-coded minus finite-difference Jacobian with tolerance "
        f"{LOCALIZATION_THRESHOLD:.12e} ----------\n"
        "Mat Object: 1 MPI process\n  type: seqaij\n"
        + "\n".join(rows)
        + "\nLinear solve did not converge due to DIVERGED_BREAKDOWN iterations 30\n"
    )


def self_test() -> int:
    try:
        prediction = predict_fd_step_quantization()
        if abs(prediction["wp_predicted_attenuation"] - 0.9640628864075022) > 1e-12:
            raise AssertionError("WP quantization predictor drifted")
        if (
            abs(prediction["ds_predicted_attenuation"] - 1.0)
            > DS_ATTENUATION_TO_UNITY_TOL
        ):
            raise AssertionError("DS electron perturbation is not representable enough")

        raw = {
            "threshold": LOCALIZATION_THRESHOLD,
            "entries": [
                {"row": 0, "col": 0, "value": 0.0},
                {"row": 4, "col": 0, "value": 2e-4},
            ],
            "section_observed": True,
        }
        filtered = nonzero_threshold_difference(raw)
        if (
            filtered["structural_entry_count"] != 2
            or filtered["nonzero_thresholded_entry_count"] != 1
        ):
            raise AssertionError("zero-valued structural entries were not excluded")

        dofmap = _synthetic_dofmap()
        directional = directional_localization(
            _synthetic_log(
                4e-5,
                ["row 0: (4, 0.0)", "row 4: (0, 2.0e-4)"],
            ),
            dofmap,
        )
        if directional["metrics"]["nonzero_thresholded_entry_count"] != 1:
            raise AssertionError("directional nonzero count is wrong")
        if directional["metrics"]["j_lambda_n"]["count"] != 1:
            raise AssertionError("J_lambda,n direction was not identified")
        if directional["metrics"]["j_n_lambda"]["count"] != 0:
            raise AssertionError("zero J_n,lambda structural entry was miscounted")

        base = _issue46_synthetic_constrained_input(TARGET)
        first_text, _ = first_linear.instrument_first_linear(base)
        baseline, _ = loc.instrument_localization(first_text)
        ds_text, _ = instrument_ds_reference(baseline)
        audit = audit_ds_reference_structure(baseline, ds_text)
        if audit["status"] != "PASS":
            blocker_ids = [item["id"] for item in audit["blockers"]]
            raise AssertionError(
                "DS observation-only structure did not pass: " + ",".join(blocker_ids)
            )
        bad = ds_text.replace("-mat_fd_type", "-mat_fd_type_bad", 1)
        if audit_ds_reference_structure(baseline, bad)["status"] == "PASS":
            raise AssertionError("FD-reference option mutation was accepted")
    except Exception as exc:
        print(f"ISSUE46_FD_REFERENCE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE46_FD_REFERENCE_SELFTEST: PASS")
    return 0


def _prepare_case(exe: Path, results_root: str | None) -> dict[str, Any]:
    base_case, base_text, radial_span = inv._base_case_context()
    base_c0 = inv._build_constrained_quasisteady_input(
        base_text,
        radial_span=radial_span,
        macro_avg=TARGET,
        runtime_observability=True,
    )
    first_text, _ = first_linear.instrument_first_linear(base_c0)
    baseline_text, _ = loc.instrument_localization(first_text)
    baseline_audit = loc.audit_localization_structure(first_text, baseline_text)
    ds_text, instrumentation = instrument_ds_reference(baseline_text)
    ds_audit = audit_ds_reference_structure(baseline_text, ds_text)

    root = inv._evidence_root(
        exe=exe,
        results_root=results_root,
        stem="issue46_fd_reference_discriminator",
    )
    case_dir = root / "c0_ds_reference"
    v2.v1._copy_case(base_case, case_dir, ds_text)
    v2.v1._validate_assets(case_dir)
    return {
        "root": root,
        "case_dir": case_dir,
        "input": case_dir / "input.i",
        "baseline_audit": baseline_audit,
        "ds_audit": ds_audit,
        "instrumentation": instrumentation,
    }


def _check_input(exe: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    path = prepared["root"] / "p2_ds_check_input.log"
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=path,
        extra_args=("--check-input", "--color", "off"),
        stream=False,
    )
    return {
        "status": "PASS" if run.returncode == 0 else "HOLD",
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(path),
        "identity": {
            **evidence.identity_record(executable=exe, input_path=prepared["input"]),
            "qpx_sha256": evidence.sha256_file(exe),
        },
    }


def _preflight(exe: Path, prepared: dict[str, Any]) -> tuple[dict[str, Any], str]:
    p1 = (
        prepared["baseline_audit"]["status"] == "PASS"
        and prepared["ds_audit"]["status"] == "PASS"
    )
    p2 = _check_input(exe, prepared) if p1 else {}
    status = "PASS" if p1 and p2.get("status") == "PASS" else "HOLD"
    return p2, status


def run_preflight(qpx: str | None, results_root: str | None) -> int:
    exe = v2.resolve_executable(qpx)
    v2.validate_executable(exe)
    prepared = _prepare_case(exe, results_root)
    p2, status = _preflight(exe, prepared)
    prediction = prepared["ds_audit"]["prediction"]
    decision_class = (
        "FD_REFERENCE_DISCRIMINATOR_READY"
        if status == "PASS"
        else "HARNESS_OR_CONSTRUCTION_FAIL"
    )
    summary = {
        "issue": ISSUE,
        "mode": "fd-reference-discriminator-preflight",
        "status": status,
        "p3_executed": False,
        "evr_consumed_by_preflight": False,
        "evr2_authorized_by_harness": False,
        "p1": {
            "baseline": prepared["baseline_audit"],
            "ds_reference": prepared["ds_audit"],
        },
        "p2": {"ds_check_input": p2},
        "prediction": prediction,
        "decision": {
            "status": status,
            "class": decision_class,
            "reason": (
                "exact C0 is preserved and only PETSc Jacobian-test reference "
                "differencing changes WP->DS"
                if status == "PASS"
                else "FD-reference discriminator failed a construction/check-input gate"
            ),
        },
    }
    path = prepared["root"] / "summary.json"
    v2._write_json(path, summary)
    print(f"ISSUE46_FD_REFERENCE_P1_BASELINE: {prepared['baseline_audit']['status']}")
    print(f"ISSUE46_FD_REFERENCE_P1_DS: {prepared['ds_audit']['status']}")
    print(f"ISSUE46_FD_REFERENCE_P2_DS_CHECK_INPUT: {p2.get('status', 'HOLD')}")
    for key, marker in (
        ("wp_requested_dx", "WP_REQUESTED_DX"),
        ("wp_representable_dx", "WP_REPRESENTABLE_DX"),
        ("wp_predicted_attenuation", "WP_PREDICTED_ATTENUATION"),
        ("ds_requested_dx", "DS_REQUESTED_DX"),
        ("ds_representable_dx", "DS_REPRESENTABLE_DX"),
        ("ds_predicted_attenuation", "DS_PREDICTED_ATTENUATION"),
    ):
        print(f"ISSUE46_FD_REFERENCE_{marker}: {prediction[key]:.12e}")
    print(f"ISSUE46_FD_REFERENCE_PREFLIGHT: {status}")
    print(f"ISSUE46_FD_REFERENCE_CLASS: {decision_class}")
    print(f"ISSUE46_FD_REFERENCE_SUMMARY: {path}")
    return 0 if status == "PASS" else 2


def _purge_dofmap(case_dir: Path) -> None:
    for path in case_dir.glob(f"{loc.DOFMAP_FILE_BASE}*.json"):
        if path.is_file():
            path.unlink()


def run_runtime(qpx: str | None, results_root: str | None) -> int:
    exe = v2.resolve_executable(qpx)
    v2.validate_executable(exe)
    prepared = _prepare_case(exe, results_root)
    p2, preflight_status = _preflight(exe, prepared)
    if preflight_status != "PASS":
        print("ISSUE46_FD_REFERENCE_PRECLASS: HOLD")
        print("ISSUE46_FD_REFERENCE_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(
            "ISSUE46_FD_REFERENCE_REASON: runtime refused because P0/P1/P2 is not PASS"
        )
        return 2

    _purge_dofmap(prepared["case_dir"])
    log_path = prepared["root"] / "p3_c0_ds_reference.log"
    print("ISSUE46_FD_REFERENCE_CASE_START: C0_DS_REFERENCE")
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=log_path,
        extra_args=("--color", "off"),
        stream=False,
    )
    print(f"ISSUE46_FD_REFERENCE_CASE_END: C0_DS_REFERENCE rc={run.returncode}")
    dofmap = prepared["case_dir"] / f"{loc.DOFMAP_FILE_BASE}.json"
    if not dofmap.is_file():
        analysis = {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": f"missing DOFMap output: {dofmap}",
        }
    else:
        analysis = analyze_ds_runtime(
            log_path.read_text(errors="replace"),
            dofmap.read_text(errors="replace"),
            returncode=run.returncode,
        )

    directional = analysis.get("directional", {})
    metrics = directional.get("metrics", {})
    jac = analysis.get("jacobian", {})
    rel = jac.get("worst_relative_frobenius_error")
    if isinstance(rel, (int, float)) and math.isfinite(float(rel)):
        print(f"ISSUE46_FD_REFERENCE_C0_JACOBIAN_REL_ERROR: {float(rel):.12e}")
    if metrics:
        print(
            "ISSUE46_FD_REFERENCE_NONZERO_DIFFERENCE_ENTRIES: "
            f"{metrics.get('nonzero_thresholded_entry_count', 0)}"
        )
        for key, label in (
            ("j_lambda_n", "J_LAMBDA_N"),
            ("j_n_lambda", "J_N_LAMBDA"),
        ):
            block = metrics.get(key, {})
            print(f"ISSUE46_FD_REFERENCE_{label}_COUNT: {block.get('count', 0)}")
            print(
                f"ISSUE46_FD_REFERENCE_{label}_L2: "
                f"{float(block.get('l2_difference', 0.0)):.12e}"
            )
            print(
                f"ISSUE46_FD_REFERENCE_{label}_MAX_ABS: "
                f"{float(block.get('max_abs_difference', 0.0)):.12e}"
            )

    summary = {
        "issue": ISSUE,
        "mode": "fd-reference-discriminator-runtime",
        "status": analysis.get("status", "HOLD"),
        "p3_executed": True,
        "evr_count_for_this_batch": 1,
        "evr_budget_owner": "#46",
        "evr_number": 2,
        "observation_change_only": {"mat_fd_type": "wp->ds"},
        "run": {
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "log": str(log_path),
            "dofmap": str(dofmap) if dofmap.is_file() else None,
            "identity": {
                **evidence.identity_record(executable=exe, input_path=prepared["input"]),
                "qpx_sha256": evidence.sha256_file(exe),
            },
        },
        "preflight": {
            "status": preflight_status,
            "p1_baseline": prepared["baseline_audit"],
            "p1_ds": prepared["ds_audit"],
            "p2_ds_check_input": p2,
        },
        "analysis": analysis,
    }
    summary_path = prepared["root"] / "summary.json"
    v2._write_json(summary_path, summary)
    print(
        "ISSUE46_FD_REFERENCE_PRECLASS: "
        + ("PASS" if analysis.get("status") == "PASS" else "HOLD")
    )
    print(
        f"ISSUE46_FD_REFERENCE_CLASS: "
        f"{analysis.get('class', 'FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT')}"
    )
    print(f"ISSUE46_FD_REFERENCE_REASON: {analysis.get('reason', 'no reason')}")
    print(f"ISSUE46_FD_REFERENCE_LOG: {log_path}")
    if dofmap.is_file():
        print(f"ISSUE46_FD_REFERENCE_DOFMAP: {dofmap}")
    print(f"ISSUE46_FD_REFERENCE_SUMMARY: {summary_path}")
    return 0 if analysis.get("status") == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Issue46 PETSc FD-reference audit")
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument(
        "--run",
        action="store_true",
        help="execute the explicitly authorized Issue46 EVR2 DS-reference discriminator",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    try:
        if args.preflight:
            return run_preflight(args.qpx, args.results_root)
        return run_runtime(args.qpx, args.results_root)
    except (
        JacobianFDReferenceAuditError,
        loc.AugmentedJacobianLocalizationError,
        inv.ElectronInventoryNullspaceError,
        MooseInputError,
        OSError,
    ) as exc:
        marker = (
            "ISSUE46_FD_REFERENCE_PREFLIGHT"
            if args.preflight
            else "ISSUE46_FD_REFERENCE_PRECLASS"
        )
        print(f"{marker}: HOLD")
        print("ISSUE46_FD_REFERENCE_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"ISSUE46_FD_REFERENCE_REASON: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
