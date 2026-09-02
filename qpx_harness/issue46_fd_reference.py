"""Semantic runtime owner for the Issue46 FD-reference audit.

Scientific FD-reference policy is owned by ``recipes.issue46_fd_reference``.
This module owns the stable runtime/preflight/evidence orchestration and composes
that policy with existing Issue45/Issue46 construction owners and generic QPX
runtime/evidence primitives.  The historical
``qpx_harness.jacobian_fd_reference_audit`` module is no longer a runtime
dependency and may remain only as a temporary test compatibility proxy while
Issue48 migrates its remaining characterization consumers.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from recipes import issue45_first_linear as first_linear_policy
from recipes import issue46_fd_reference as recipe
from recipes import issue46_jacobian_localization as localization_recipe

from .evidence import artifacts
from . import electron_inventory_nullspace as inv
from . import evidence
from . import issue46_jacobian_localization as localization_runtime
from .moose import dofmap as dm
from .moose.input import MooseInputError
from .petsc import matrix as petsc_matrix
from .petsc import options as petsc_options
from .execution.runtime import resolve_executable, run_qpx, validate_executable

ISSUE = recipe.ISSUE
TARGET = recipe.TARGET
HISTORICAL_EVR1_ELECTRON_DOF_COUNT = recipe.HISTORICAL_EVR1_ELECTRON_DOF_COUNT
PETSC_REFERENCE_VERSION = recipe.PETSC_REFERENCE_VERSION
FD_REFERENCE_TYPE = recipe.FD_REFERENCE_TYPE
GLOBAL_JACOBIAN_REL_TOL = recipe.GLOBAL_JACOBIAN_REL_TOL
LOCALIZATION_THRESHOLD = recipe.LOCALIZATION_THRESHOLD
DOFMAP_FILE_BASE = localization_recipe.DOFMAP_FILE_BASE
SQRT_MACHINE_EPSILON = math.sqrt(sys.float_info.epsilon)
DS_ATTENUATION_TO_UNITY_TOL = recipe.DS_ATTENUATION_TO_UNITY_TOL


class JacobianFDReferenceAuditError(RuntimeError):
    """Runtime-orchestration error preserving the historical public contract."""


def _runtime_error_adapter(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Adapt recipe policy errors to the historical runtime exception contract."""
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except recipe.Issue46FDReferenceError as exc:
            raise JacobianFDReferenceAuditError(str(exc)) from exc

    setattr(wrapped, "__qpx_recipe_target__", fn)
    return wrapped


predict_fd_step_quantization = _runtime_error_adapter(recipe.predict_fd_step_quantization)
_historical_evr1_prediction = recipe.historical_evr1_prediction
_historical_mechanism_evidence = recipe.historical_mechanism_evidence
_termination_admissibility = recipe.termination_admissibility
_runtime_mechanism_applicability = recipe.runtime_mechanism_applicability
_evidence_provenance_status = recipe.evidence_provenance_status
directional_localization = _runtime_error_adapter(recipe.directional_localization)
instrument_ds_reference = _runtime_error_adapter(recipe.instrument_ds_reference)
_remove_fd_type_pair = _runtime_error_adapter(recipe.remove_fd_type_pair)
_mask_petsc_pair_lines = _runtime_error_adapter(recipe.mask_petsc_pair_lines)
analyze_ds_runtime = recipe.analyze_ds_runtime


def _is_recipe_adapter(bound: Callable[..., Any], target: Callable[..., Any]) -> bool:
    return getattr(bound, "__qpx_recipe_target__", None) is target


def recipe_backing_status() -> dict[str, bool]:
    """Return identity/backing checks for the semantic policy surface."""
    return {
        "predict_fd_step_quantization": _is_recipe_adapter(
            predict_fd_step_quantization, recipe.predict_fd_step_quantization
        ),
        "historical_evr1_prediction": _historical_evr1_prediction
        is recipe.historical_evr1_prediction,
        "historical_mechanism_evidence": _historical_mechanism_evidence
        is recipe.historical_mechanism_evidence,
        "termination_admissibility": _termination_admissibility
        is recipe.termination_admissibility,
        "runtime_mechanism_applicability": _runtime_mechanism_applicability
        is recipe.runtime_mechanism_applicability,
        "evidence_provenance_status": _evidence_provenance_status
        is recipe.evidence_provenance_status,
        "directional_localization": _is_recipe_adapter(
            directional_localization, recipe.directional_localization
        ),
        "instrument_ds_reference": _is_recipe_adapter(
            instrument_ds_reference, recipe.instrument_ds_reference
        ),
        "remove_fd_type_pair": _is_recipe_adapter(
            _remove_fd_type_pair, recipe.remove_fd_type_pair
        ),
        "mask_petsc_pair_lines": _is_recipe_adapter(
            _mask_petsc_pair_lines, recipe.mask_petsc_pair_lines
        ),
        "analyze_ds_runtime": analyze_ds_runtime is recipe.analyze_ds_runtime,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    artifacts.write_json_bundle(path.parent, {"summary": (path.name, payload)})


def _issue46_synthetic_constrained_input(macro_avg: float = TARGET) -> str:
    """Build the Issue46 synthetic C0 fixture without mutating Issue45 ownership."""
    text = inv._synthetic_constrained_input(macro_avg)
    return inv._set_or_insert_parameter(
        text,
        "Variables/n_e",
        "initial_condition",
        f"{TARGET:.17g}",
    )


def nonzero_threshold_difference(difference: dict[str, Any]) -> dict[str, Any]:
    """Preserve the accepted structural/nonzero difference result surface."""
    return petsc_matrix.finite_nonzero_entries(difference)


def audit_ds_reference_structure(
    baseline_text: str, ds_text: str
) -> dict[str, Any]:
    """Validate that the DS case is an observation-only mutation of C0."""
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
            "prediction": _historical_evr1_prediction(),
            "mechanism_evidence": _historical_mechanism_evidence(),
            "closure": {},
        }

    expected_pairs = baseline_pairs + [("-mat_fd_type", FD_REFERENCE_TYPE)]
    add("ds-petsc-pair-exact", ds_pairs == expected_pairs, ds_pairs, expected_pairs)
    add(
        "petsc-flags-preserved",
        petsc_options.get_flags(ds_text) == petsc_options.get_flags(baseline_text),
        petsc_options.get_flags(ds_text),
        petsc_options.get_flags(baseline_text),
    )

    restored: str | None = None
    try:
        restored = _remove_fd_type_pair(ds_text)
        restored_pairs = petsc_options.get_name_value_pairs(restored)
        semantic_pair_restore = restored_pairs == baseline_pairs
        masked_byte_equal = _mask_petsc_pair_lines(restored) == _mask_petsc_pair_lines(
            baseline_text
        )
    except (
        JacobianFDReferenceAuditError,
        inv.ElectronInventoryNullspaceError,
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

    prediction = _historical_evr1_prediction()
    mechanism = _historical_mechanism_evidence()
    add(
        "historical-wp-mechanism-characterized",
        mechanism["status"] == "PASS",
        mechanism["class"],
        "WP_QUANTIZATION_MECHANISM_CHARACTERIZED",
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
        "mechanism_evidence": mechanism,
        "closure": closure,
    }


def _synthetic_dofmap() -> str:
    return json.dumps(
        {
            "ndof": 5,
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
        backing = recipe_backing_status()
        failed_backing = sorted(name for name, ok in backing.items() if not ok)
        if failed_backing:
            raise AssertionError(f"recipe backing drift: {failed_backing}")

        prediction = _historical_evr1_prediction()
        if (
            abs(prediction["ds_predicted_attenuation"] - 1.0)
            > DS_ATTENUATION_TO_UNITY_TOL
        ):
            raise AssertionError("DS electron perturbation is not representable enough")
        mechanism = _historical_mechanism_evidence()
        if mechanism["class"] != "WP_QUANTIZATION_MECHANISM_CHARACTERIZED":
            raise AssertionError("historical WP mechanism evidence contract drifted")

        explicit = predict_fd_step_quantization(vector_norm=123.0, component_value=7.0)
        if explicit["wp_requested_dx"] != math.sqrt(124.0) * SQRT_MACHINE_EPSILON:
            raise AssertionError("WP predictor ignored the explicit vector norm")
        if explicit["ds_requested_dx"] != 7.0 * SQRT_MACHINE_EPSILON:
            raise AssertionError("DS predictor ignored the explicit component value")

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
        first_text, _ = first_linear_policy.instrument_first_linear(base)
        baseline, _ = localization_recipe.instrument_localization(first_text)
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

        expected_termination = _termination_admissibility(
            _synthetic_log(5.0e-11, []), returncode=1
        )
        if expected_termination["class"] != "EXPECTED_DIAGNOSTIC_NONCONVERGENCE":
            raise AssertionError("expected DIVERGED_BREAKDOWN termination was rejected")
        fatal_termination = _termination_admissibility(
            _synthetic_log(5.0e-11, []) + "Segmentation fault (core dumped)\n",
            returncode=139,
        )
        if fatal_termination["class"] != "FATAL_RUNTIME_FAILURE":
            raise AssertionError("fatal runtime signature was accepted")

        provenance_root = Path("/tmp/issue46-evidence")
        provenance_case = provenance_root / "c0_ds_reference"
        provenance_input = provenance_case / "input.i"
        provenance_log = provenance_root / "p3_c0_ds_reference.log"
        provenance_dofmap = provenance_case / f"{DOFMAP_FILE_BASE}.json"
        provenance = _evidence_provenance_status(
            root=provenance_root,
            case_dir=provenance_case,
            input_path=provenance_input,
            source_case=Path("/tmp/issue46-source-case"),
            input_sha_before="abc",
            input_sha_after="abc",
            log_path=provenance_log,
            log_preexisting=False,
            log_exists=True,
            dofmap_path=provenance_dofmap,
            dofmap_preexisting=False,
            dofmap_exists=True,
            source_dofmaps_before=(),
            source_dofmaps_after=(),
        )
        if provenance["class"] != "EVIDENCE_PROVENANCE_PASS":
            raise AssertionError("fresh runner-owned evidence provenance was rejected")
        stale_provenance = _evidence_provenance_status(
            root=provenance_root,
            case_dir=provenance_case,
            input_path=provenance_input,
            source_case=Path("/tmp/issue46-source-case"),
            input_sha_before="abc",
            input_sha_after="abc",
            log_path=provenance_log,
            log_preexisting=True,
            log_exists=True,
            dofmap_path=provenance_dofmap,
            dofmap_preexisting=False,
            dofmap_exists=True,
            source_dofmaps_before=(),
            source_dofmaps_after=(),
        )
        if stale_provenance["class"] != "EVIDENCE_PROVENANCE_HOLD":
            raise AssertionError("stale pre-existing runtime log was accepted")
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
    first_text, _ = first_linear_policy.instrument_first_linear(base_c0)
    baseline_text, _ = localization_recipe.instrument_localization(first_text)
    baseline_audit = localization_runtime.audit_localization_structure(
        first_text, baseline_text
    )
    ds_text, instrumentation = instrument_ds_reference(baseline_text)
    ds_audit = audit_ds_reference_structure(baseline_text, ds_text)
    identity_status = (
        baseline_audit["status"] == "PASS" and ds_audit["status"] == "PASS"
    )
    experiment_identity = {
        "status": "PASS" if identity_status else "HOLD",
        "class": (
            "ISSUE46_EXPERIMENT_IDENTITY_PASS"
            if identity_status
            else "ISSUE46_EXPERIMENT_IDENTITY_DRIFT"
        ),
        "reason": (
            "the prepared C0 case preserves the accepted constrained closure and WP-to-DS observation-only contract"
            if identity_status
            else "the prepared C0 case failed a material Issue46 semantic identity gate"
        ),
        "target": TARGET,
        "observation_change": {"mat_fd_type": "wp->ds"},
    }

    root = inv._evidence_root(
        exe=exe,
        results_root=results_root,
        stem="issue46_fd_reference_discriminator",
    )
    case_dir = root / "c0_ds_reference"
    inv._stage_case(base_case, case_dir, ds_text)
    input_path = case_dir / "input.i"
    return {
        "root": root,
        "case_dir": case_dir,
        "input": input_path,
        "source_case": base_case,
        "input_sha256": evidence.sha256_file(input_path),
        "baseline_audit": baseline_audit,
        "ds_audit": ds_audit,
        "instrumentation": instrumentation,
        "experiment_identity": experiment_identity,
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
        and prepared["experiment_identity"]["status"] == "PASS"
    )
    p2 = _check_input(exe, prepared) if p1 else {}
    status = "PASS" if p1 and p2.get("status") == "PASS" else "HOLD"
    return p2, status


def run_preflight(qpx: str | None, results_root: str | None) -> int:
    exe = resolve_executable(qpx)
    validate_executable(exe)
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
            "experiment_identity": prepared["experiment_identity"],
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
    _write_json(path, summary)
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
    for path in case_dir.glob(f"{DOFMAP_FILE_BASE}*.json"):
        if path.is_file():
            path.unlink()


def _source_dofmaps(source_case: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(path.resolve())
            for path in source_case.glob(f"{DOFMAP_FILE_BASE}*.json")
            if path.is_file()
        )
    )


def run_runtime(qpx: str | None, results_root: str | None) -> int:
    exe = resolve_executable(qpx)
    validate_executable(exe)
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
    dofmap = prepared["case_dir"] / f"{DOFMAP_FILE_BASE}.json"
    log_preexisting = log_path.exists()
    dofmap_preexisting = dofmap.exists()
    source_dofmaps_before = _source_dofmaps(prepared["source_case"])
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
    input_sha_after = (
        evidence.sha256_file(prepared["input"])
        if prepared["input"].is_file()
        else "MISSING"
    )
    source_dofmaps_after = _source_dofmaps(prepared["source_case"])
    provenance = _evidence_provenance_status(
        root=prepared["root"],
        case_dir=prepared["case_dir"],
        input_path=prepared["input"],
        source_case=prepared["source_case"],
        input_sha_before=prepared["input_sha256"],
        input_sha_after=input_sha_after,
        log_path=log_path,
        log_preexisting=log_preexisting,
        log_exists=log_path.is_file(),
        dofmap_path=dofmap,
        dofmap_preexisting=dofmap_preexisting,
        dofmap_exists=dofmap.is_file(),
        source_dofmaps_before=source_dofmaps_before,
        source_dofmaps_after=source_dofmaps_after,
    )
    if provenance["status"] != "PASS":
        analysis = {
            "status": "HOLD",
            "class": "EVIDENCE_PROVENANCE_HOLD",
            "reason": provenance["reason"],
            "evidence_provenance": provenance,
        }
    elif not dofmap.is_file():
        analysis = {
            "status": "HOLD",
            "class": "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "reason": f"missing DOFMap output: {dofmap}",
            "evidence_provenance": provenance,
        }
    else:
        log_text = log_path.read_text(errors="replace")
        analysis = analyze_ds_runtime(
            log_text,
            dofmap.read_text(errors="replace"),
            returncode=run.returncode,
            experiment_identity=prepared["experiment_identity"],
        )
        analysis["evidence_provenance"] = provenance

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

    if prepared["input"].is_file():
        run_identity = {
            **evidence.identity_record(executable=exe, input_path=prepared["input"]),
            "qpx_sha256": evidence.sha256_file(exe),
        }
    else:
        run_identity = {
            "qpx_realpath": str(exe.resolve()),
            "input_realpath": str(prepared["input"].resolve()),
            "input_sha256": "MISSING",
            "qpx_sha256": evidence.sha256_file(exe),
        }
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
            "identity": run_identity,
            "evidence_provenance": provenance,
        },
        "preflight": {
            "status": preflight_status,
            "p1_baseline": prepared["baseline_audit"],
            "p1_ds": prepared["ds_audit"],
            "p1_experiment_identity": prepared["experiment_identity"],
            "p2_ds_check_input": p2,
        },
        "analysis": analysis,
    }
    summary_path = prepared["root"] / "summary.json"
    _write_json(summary_path, summary)
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
        localization_runtime.Issue46JacobianLocalizationError,
        dm.DofMapError,
        petsc_matrix.MatrixParseError,
        petsc_options.PetscOptionsError,
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
