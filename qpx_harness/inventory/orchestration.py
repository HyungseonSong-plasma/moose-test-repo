"""P0/P1/P2/P3 orchestration and evidence assembly for inventory closure."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from recipes import issue45_closure_basis as closure_basis

from ..reasoning import diagnose_coupled_runtime_evidence
from ..evidence import artifacts
from ..execution import cases as case_ops
from .. import evidence
from ..execution.runtime import resolve_executable, run_command, run_qpx, validate_executable
from ..moose import check_input as check_input_diagnostic
from ..analysis.scale_audit import mesh_stats
from .closure_model import (
    _build_constrained_quasisteady_input,
    _target_only_pair_audit,
)
from .closure_runtime import (
    _evaluate_runtime_case_data,
    _evaluate_runtime_pair,
    _find_runtime_csv,
    _read_final_runtime_row,
)
from .closure_schema import analyze_constraint_schema_text, analyze_drift_schema_text
from .constants import (
    BASE_CASE_RELATIVE,
    C0_TARGET,
    C1_TARGET,
    CLOSURE_DELTA_REL_TOL,
    CLOSURE_TARGET_REL_TOL,
    CONSTRAINT_TYPE,
    DRIFT_TYPE,
    DT_REFERENCE,
    INVENTORY_CONSISTENCY_REL_TOL,
    ISSUE,
    RUNTIME_PURGE_DIRECTORY_NAMES,
    RUNTIME_PURGE_PATTERNS,
    STEPS,
)
from .errors import ElectronInventoryNullspaceError
from .structure import (
    audit_closed_electron_structure,
    audit_constrained_quasisteady_structure,
)


def _write_json(path: Path, payload: object) -> None:
    artifacts.write_json_bundle(path.parent, {"summary": (path.name, payload)})


def _stage_case(source: Path, target: Path, input_text: str) -> list[str]:
    try:
        case_ops.stage_case(
            source,
            target,
            input_text=input_text,
            purge_directory_names=RUNTIME_PURGE_DIRECTORY_NAMES,
            purge_patterns=RUNTIME_PURGE_PATTERNS,
        )
        refs = case_ops.validate_case_references(target)
    except case_ops.CaseError as exc:
        raise ElectronInventoryNullspaceError(f"case staging failed: {exc}") from exc
    return [ref["resolved"] for ref in refs]


def _base_case_context() -> tuple[Path, str, float]:
    repo_root = Path(__file__).resolve().parents[2]
    base_case = repo_root / BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise ElectronInventoryNullspaceError(f"missing accepted electron control: {base_case}")
    mesh = mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    return base_case, (base_case / "input.i").read_text(), radial_span


def _evidence_root(*, exe: Path, results_root: str | None, stem: str) -> Path:
    root_parent = (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    return evidence.ensure_fresh_directory(
        root_parent / f"{stem}_{evidence.utc_timestamp()}"
    )


def _prepare_case(*, exe: Path, results_root: str | None) -> dict[str, Any]:
    base_case, base_text, radial_span = _base_case_context()
    text, feedback_meta = closure_basis.build_closed_feedback_input(
        base_text,
        dt=DT_REFERENCE,
        steps=STEPS,
        radial_span=radial_span,
    )
    p1 = audit_closed_electron_structure(text)
    root = _evidence_root(
        exe=exe, results_root=results_root, stem="issue45_inventory_nullspace"
    )
    case_dir = root / "case"
    _stage_case(base_case, case_dir, text)
    return {
        "root": root,
        "case_dir": case_dir,
        "input_path": case_dir / "input.i",
        "p1": p1,
        "feedback_basis": feedback_meta,
    }


def _prepare_closure_case(
    *, exe: Path, results_root: str | None, macro_avg: float
) -> dict[str, Any]:
    base_case, base_text, radial_span = _base_case_context()
    text = _build_constrained_quasisteady_input(
        base_text,
        radial_span=radial_span,
        macro_avg=macro_avg,
    )
    p1 = audit_constrained_quasisteady_structure(text, expected_macro_avg=macro_avg)
    root = _evidence_root(
        exe=exe, results_root=results_root, stem="issue45_inventory_closure"
    )
    case_dir = root / "case"
    _stage_case(base_case, case_dir, text)
    return {
        "root": root,
        "case_dir": case_dir,
        "input_path": case_dir / "input.i",
        "p1": p1,
        "macro_electron_average": macro_avg,
    }


def _prepare_closure_runtime_cases(
    *, exe: Path, results_root: str | None
) -> dict[str, Any]:
    base_case, base_text, radial_span = _base_case_context()
    root = _evidence_root(
        exe=exe,
        results_root=results_root,
        stem="issue45_inventory_closure_runtime",
    )
    cases: dict[str, Any] = {}
    for label, target in (("C0_reference", C0_TARGET), ("C1_shift", C1_TARGET)):
        text = _build_constrained_quasisteady_input(
            base_text,
            radial_span=radial_span,
            macro_avg=target,
            runtime_observability=True,
        )
        p1 = audit_constrained_quasisteady_structure(text, expected_macro_avg=target)
        case_dir = root / "cases" / label
        _stage_case(base_case, case_dir, text)
        cases[label] = {
            "target": target,
            "text": text,
            "case_dir": case_dir,
            "input_path": case_dir / "input.i",
            "p1": p1,
        }
    pair = _target_only_pair_audit(
        cases["C0_reference"]["text"], cases["C1_shift"]["text"]
    )
    return {"root": root, "cases": cases, "pair": pair}


def _run_p2_check_input(
    *, exe: Path, prepared: dict[str, Any], log_path: Path | None = None
) -> dict[str, Any]:
    actual_log = log_path or (prepared["root"] / "p2_check_input.log")
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=actual_log,
        extra_args=("--check-input", "--color", "off"),
        stream=False,
    )
    return {
        "status": "PASS" if run.returncode == 0 else "HOLD",
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(actual_log),
        "failure": check_input_diagnostic.classify_failure(actual_log, run.returncode),
        "identity": {
            **evidence.identity_record(executable=exe, input_path=prepared["input_path"]),
            "qpx_sha256": evidence.sha256_file(exe),
        },
    }


def _run_schema_query(
    *,
    exe: Path,
    prepared: dict[str, Any],
    object_type: str,
    analyzer: Any,
    log_name: str,
) -> dict[str, Any]:
    log_path = prepared["root"] / log_name
    run = run_command(
        [str(exe), "--json-search", object_type],
        cwd=prepared["case_dir"],
        log_path=log_path,
        stream=False,
    )
    analysis = analyzer(
        log_path.read_text(errors="replace") if log_path.is_file() else "",
        returncode=run.returncode,
    )
    return {
        **analysis,
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log_path),
        "qpx_realpath": str(exe),
        "qpx_sha256": evidence.sha256_file(exe),
    }


def run_preflight(*, qpx: str | None, results_root: str | None) -> int:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    prepared = _prepare_case(exe=exe, results_root=results_root)
    p1_pass = prepared["p1"]["status"] == "PASS"
    check_input = _run_p2_check_input(exe=exe, prepared=prepared) if p1_pass else {}
    schema = (
        _run_schema_query(
            exe=exe,
            prepared=prepared,
            object_type=DRIFT_TYPE,
            analyzer=analyze_drift_schema_text,
            log_name="p2_drift_schema.log",
        )
        if p1_pass
        else {}
    )
    p2_check_pass = check_input.get("status") == "PASS"
    p2_schema_pass = schema.get("status") == "PASS"
    status = "PASS" if p1_pass and p2_check_pass and p2_schema_pass else "HOLD"
    decision = {
        "status": status,
        "class": (
            "INVENTORY_LEFT_NULLSPACE_STATIC_PASS"
            if status == "PASS"
            else "CONSERVATION_STRUCTURE_FAIL"
            if not p1_pass
            else schema.get("class", "HARNESS_OR_CONSTRUCTION_FAIL")
            if not p2_schema_pass
            else "HARNESS_OR_CONSTRUCTION_FAIL"
        ),
        "reason": (
            "the generated closed/source-free electron residual satisfies the structural conservation contract, and user-local QPX schema confirms the custom drift exposes FVFluxKernel conservative boundary-execution semantics"
            if status == "PASS"
            else "P0/P1/P2 did not complete the static/framework conservation chain"
        ),
        "left_null_vector": "[1^T, 0]" if status == "PASS" else None,
        "identity": (
            "[1^T,0] J_steady = 0 for the current reduced closed/source-free model"
            if status == "PASS"
            else None
        ),
        "p3_required_for_this_identity": False,
    }
    summary_path = prepared["root"] / "summary.json"
    _write_json(
        summary_path,
        {
            "issue": ISSUE,
            "mode": "inventory-nullspace-preflight",
            "status": status,
            "p3_executed": False,
            "claim": "static/framework proof of the electron-inventory left-null identity for the current closed/source-free reduced model",
            "feedback_basis": prepared.get("feedback_basis"),
            "p1": prepared["p1"],
            "p2": {"check_input": check_input, "drift_schema": schema},
            "decision": decision,
        },
    )
    print(f"ISSUE45_INVENTORY_NULLSPACE_P1: {'PASS' if p1_pass else 'HOLD'}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_P2_CHECK_INPUT: {'PASS' if p2_check_pass else 'HOLD'}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_P2_DRIFT_SCHEMA: {'PASS' if p2_schema_pass else 'HOLD'}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_PREFLIGHT: {status}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_CLASS: {decision['class']}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_REASON: {decision['reason']}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_SUMMARY: {summary_path}")
    return 0 if status == "PASS" else 2


def run_closure_preflight(
    *, qpx: str | None, results_root: str | None, macro_avg: float
) -> int:
    if not math.isfinite(macro_avg) or macro_avg <= 0.0:
        raise ElectronInventoryNullspaceError("macro electron average must be finite and positive")
    exe = resolve_executable(qpx)
    validate_executable(exe)
    prepared = _prepare_closure_case(
        exe=exe, results_root=results_root, macro_avg=macro_avg
    )
    p1_pass = prepared["p1"]["status"] == "PASS"
    check_input = _run_p2_check_input(exe=exe, prepared=prepared) if p1_pass else {}
    schema = (
        _run_schema_query(
            exe=exe,
            prepared=prepared,
            object_type=CONSTRAINT_TYPE,
            analyzer=analyze_constraint_schema_text,
            log_name="p2_constraint_schema.log",
        )
        if p1_pass
        else {}
    )
    p2_check_pass = check_input.get("status") == "PASS"
    p2_schema_pass = schema.get("status") == "PASS"
    status = "PASS" if p1_pass and p2_check_pass and p2_schema_pass else "HOLD"
    decision = {
        "status": status,
        "class": (
            "CONSTRAINED_QUASISTEADY_CLOSURE_READY"
            if status == "PASS"
            else "CLOSURE_STRUCTURE_FAIL"
            if not p1_pass
            else schema.get("class", "HARNESS_OR_CONSTRUCTION_FAIL")
            if not p2_schema_pass
            else "HARNESS_OR_CONSTRUCTION_FAIL"
        ),
        "reason": (
            "the generated steady electron-Poisson candidate removes FVTimeKernel, adds one scalar Lagrange multiplier, and uses FVIntegralValueConstraint to preserve the declared macrostate electron average while QPX accepts the input and exposes the required constraint schema"
            if status == "PASS"
            else "P0/P1/P2 did not complete the constrained quasi-steady closure representation chain"
        ),
        "physical_constraint": "integral_Omega n_e dV = V_plasma * n_e_macro_avg",
        "macro_electron_average": macro_avg,
        "p3_executed": False,
        "p3_authorized": False,
    }
    summary_path = prepared["root"] / "summary.json"
    _write_json(
        summary_path,
        {
            "issue": ISSUE,
            "mode": "inventory-closure-preflight",
            "status": status,
            "p3_executed": False,
            "claim": "construction/framework readiness of the physically derived constrained quasi-steady electron-Poisson closure",
            "macro_electron_average": macro_avg,
            "p1": prepared["p1"],
            "p2": {"check_input": check_input, "constraint_schema": schema},
            "decision": decision,
        },
    )
    print(f"ISSUE45_INVENTORY_CLOSURE_P1: {'PASS' if p1_pass else 'HOLD'}")
    print(f"ISSUE45_INVENTORY_CLOSURE_P2_CHECK_INPUT: {'PASS' if p2_check_pass else 'HOLD'}")
    print(f"ISSUE45_INVENTORY_CLOSURE_P2_CONSTRAINT_SCHEMA: {'PASS' if p2_schema_pass else 'HOLD'}")
    print(f"ISSUE45_INVENTORY_CLOSURE_PREFLIGHT: {status}")
    print(f"ISSUE45_INVENTORY_CLOSURE_CLASS: {decision['class']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_REASON: {decision['reason']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_SUMMARY: {summary_path}")
    return 0 if status == "PASS" else 2


def _closure_runtime_preflight_result(
    *, qpx: str | None, results_root: str | None
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any], str]:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    prepared = _prepare_closure_runtime_cases(exe=exe, results_root=results_root)
    p1_pass = all(case["p1"]["status"] == "PASS" for case in prepared["cases"].values())
    pair_pass = prepared["pair"]["status"] == "PASS"
    p2: dict[str, Any] = {}
    if p1_pass and pair_pass:
        for label, case in prepared["cases"].items():
            p2[label] = _run_p2_check_input(
                exe=exe,
                prepared={"root": prepared["root"], **case},
                log_path=prepared["root"] / f"p2_{label}.log",
            )
    p2_pass = bool(p2) and all(item["status"] == "PASS" for item in p2.values())
    c0 = prepared["cases"]["C0_reference"]
    schema = (
        _run_schema_query(
            exe=exe,
            prepared={"root": prepared["root"], **c0},
            object_type=CONSTRAINT_TYPE,
            analyzer=analyze_constraint_schema_text,
            log_name="p2_constraint_schema.log",
        )
        if p1_pass and pair_pass
        else {}
    )
    schema_pass = schema.get("status") == "PASS"
    status = "PASS" if p1_pass and pair_pass and p2_pass and schema_pass else "HOLD"
    return exe, prepared, p2, schema, status


def _emit_closure_runtime_preflight_markers(
    *, prepared: dict[str, Any], p2: dict[str, Any], schema: dict[str, Any],
    status: str, summary_path: Path,
) -> None:
    for label in ("C0_reference", "C1_shift"):
        print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_P1_{label}: {prepared['cases'][label]['p1']['status']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_P1_PAIR: {prepared['pair']['status']}")
    for label in ("C0_reference", "C1_shift"):
        print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_P2_{label}: {p2.get(label, {}).get('status', 'HOLD')}")
    print("ISSUE45_INVENTORY_CLOSURE_RUNTIME_P2_CONSTRAINT_SCHEMA: " + schema.get("status", "HOLD"))
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_PREFLIGHT: {status}")
    print("ISSUE45_INVENTORY_CLOSURE_RUNTIME_CLASS: " + ("CLOSURE_RUNTIME_BATCH_READY" if status == "PASS" else "HARNESS_OR_CONSTRUCTION_FAIL"))
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_SUMMARY: {summary_path}")


def run_closure_runtime_preflight(*, qpx: str | None, results_root: str | None) -> int:
    _, prepared, p2, schema, status = _closure_runtime_preflight_result(
        qpx=qpx, results_root=results_root
    )
    summary_path = prepared["root"] / "summary.json"
    _write_json(
        summary_path,
        {
            "issue": ISSUE,
            "mode": "inventory-closure-runtime-preflight",
            "status": status,
            "p3_executed": False,
            "p3_authorized_by_harness": False,
            "targets": {"C0_reference": C0_TARGET, "C1_shift": C1_TARGET},
            "acceptance": {
                "target_relative_tolerance": CLOSURE_TARGET_REL_TOL,
                "delta_relative_tolerance": CLOSURE_DELTA_REL_TOL,
                "inventory_consistency_relative_tolerance": INVENTORY_CONSISTENCY_REL_TOL,
            },
            "p1": {label: case["p1"] for label, case in prepared["cases"].items()},
            "pair_contract": prepared["pair"],
            "p2": {"check_input": p2, "constraint_schema": schema},
            "decision": {
                "status": status,
                "class": "CLOSURE_RUNTIME_BATCH_READY" if status == "PASS" else "HARNESS_OR_CONSTRUCTION_FAIL",
                "reason": (
                    "C0/C1 constrained steady cases pass structural equivalence, user-local check-input, and constraint-schema gates"
                    if status == "PASS"
                    else "C0/C1 runtime batch did not pass all P0/P1/P2 construction gates"
                ),
            },
        },
    )
    _emit_closure_runtime_preflight_markers(
        prepared=prepared, p2=p2, schema=schema, status=status, summary_path=summary_path
    )
    return 0 if status == "PASS" else 2


def _runtime_case(*, exe: Path, case: dict[str, Any], root: Path, label: str) -> dict[str, Any]:
    log_path = root / f"p3_{label}.log"
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_CASE_START: {label}")
    run = run_qpx(
        exe,
        cwd=case["case_dir"],
        input_name="input.i",
        log_path=log_path,
        extra_args=("--color", "off"),
        stream=True,
    )
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_CASE_END: {label} rc={run.returncode}")
    log_text = log_path.read_text(errors="replace") if log_path.is_file() else ""
    runtime_facts = evidence.runtime_core_facts(
        log_text,
        returncode=run.returncode,
        coupled_scaling_variables=("n_e", "potential_plasma"),
    )
    diagnostic = diagnose_coupled_runtime_evidence(runtime_facts)
    converged_marker = "Solve Converged!" in log_text or "Nonlinear solve converged due to" in log_text
    row = None
    csv_path = None
    if run.returncode == 0:
        try:
            csv_path = _find_runtime_csv(case["case_dir"])
            row = _read_final_runtime_row(csv_path)
        except ElectronInventoryNullspaceError:
            row = None
    evaluation = _evaluate_runtime_case_data(
        target=float(case["target"]),
        returncode=run.returncode,
        converged_marker=converged_marker,
        diagnostic=diagnostic,
        row=row,
    )
    return {
        "target": case["target"],
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log_path),
        "csv": str(csv_path) if csv_path else None,
        "input_identity": {
            **evidence.identity_record(executable=exe, input_path=case["input_path"]),
            "qpx_sha256": evidence.sha256_file(exe),
        },
        "diagnostic": diagnostic,
        "evaluation": evaluation,
    }


def run_closure_runtime(*, qpx: str | None, results_root: str | None) -> int:
    exe, prepared, p2, schema, preflight_status = _closure_runtime_preflight_result(
        qpx=qpx, results_root=results_root
    )
    summary_path = prepared["root"] / "summary.json"
    if preflight_status != "PASS":
        _write_json(
            summary_path,
            {
                "issue": ISSUE,
                "mode": "inventory-closure-runtime",
                "status": "HOLD",
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "p3_executed": False,
                "p1": {label: case["p1"] for label, case in prepared["cases"].items()},
                "pair_contract": prepared["pair"],
                "p2": {"check_input": p2, "constraint_schema": schema},
            },
        )
        _emit_closure_runtime_preflight_markers(
            prepared=prepared, p2=p2, schema=schema, status="HOLD", summary_path=summary_path
        )
        return 2

    print("ISSUE45_INVENTORY_CLOSURE_RUNTIME_PREFLIGHT: PASS")
    runtime = {
        label: _runtime_case(
            exe=exe, case=prepared["cases"][label], root=prepared["root"], label=label
        )
        for label in ("C0_reference", "C1_shift")
    }
    c0 = runtime["C0_reference"]["evaluation"]
    c1 = runtime["C1_shift"]["evaluation"]
    decision = _evaluate_runtime_pair(c0, c1, target0=C0_TARGET, target1=C1_TARGET)
    _write_json(
        summary_path,
        {
            "issue": ISSUE,
            "mode": "inventory-closure-runtime",
            "status": decision["status"],
            "class": decision["class"],
            "p3_executed": True,
            "evr_count_for_this_batch": 1,
            "scope": "one bounded two-target constrained steady discriminator for the current closed/source-free reduced electron-Poisson model",
            "targets": {"C0_reference": C0_TARGET, "C1_shift": C1_TARGET},
            "acceptance": {
                "target_relative_tolerance": CLOSURE_TARGET_REL_TOL,
                "delta_relative_tolerance": CLOSURE_DELTA_REL_TOL,
                "inventory_consistency_relative_tolerance": INVENTORY_CONSISTENCY_REL_TOL,
            },
            "p1": {label: case["p1"] for label, case in prepared["cases"].items()},
            "pair_contract": prepared["pair"],
            "p2": {"check_input": p2, "constraint_schema": schema},
            "runtime": runtime,
            "decision": decision,
        },
    )
    for marker, evaluation in (("C0", c0), ("C1", c1)):
        print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_{marker}: " + ("PASS" if evaluation["status"] == "PASS" else "HOLD"))
        if "average_relative_error" in evaluation:
            print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_{marker}_TARGET_REL_ERROR: {evaluation['average_relative_error']:.12e}")
    delta_pass = decision.get("status") == "PASS"
    print("ISSUE45_INVENTORY_CLOSURE_RUNTIME_DELTA_TRACKING: " + ("PASS" if delta_pass else "HOLD"))
    if "delta_relative_error" in decision:
        print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_DELTA_REL_ERROR: {decision['delta_relative_error']:.12e}")
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_PRECLASS: {decision['status']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_CLASS: {decision['class']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_REASON: {decision['reason']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_C0_LOG: {runtime['C0_reference']['log']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_C1_LOG: {runtime['C1_shift']['log']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_SUMMARY: {summary_path}")
    return 0 if decision["status"] == "PASS" else 2
