"""P1/P2/P3 orchestration for the inventory first-linear diagnostic."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from recipes import issue45_closure_basis as closure_basis
from recipes import issue45_first_linear as first_linear_recipe

from ..evidence import artifacts
from ..execution import cases as case_ops
from .. import evidence
from ..execution.runtime import resolve_executable, run_qpx, validate_executable
from ..analysis.scale_audit import mesh_stats
from ..spec.cases import QVT_PREPOISSON_CASE
from .constants import RUNTIME_PURGE_DIRECTORY_NAMES, RUNTIME_PURGE_PATTERNS
from .first_linear_structure import audit_first_linear_structure

ISSUE = first_linear_recipe.ISSUE
TARGET = first_linear_recipe.TARGET
instrument_first_linear = first_linear_recipe.instrument_first_linear
analyze_first_linear_text = first_linear_recipe.analyze_first_linear_text


def _base_case_context() -> tuple[Path, str, float]:
    repo_root = Path(__file__).resolve().parents[2]
    base_case = repo_root / QVT_PREPOISSON_CASE
    if not base_case.is_dir():
        raise first_linear_recipe.Issue45FirstLinearError(
            f"missing accepted electron control: {base_case}"
        )
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


def _stage_case(source: Path, target: Path, input_text: str) -> None:
    try:
        case_ops.stage_case(
            source,
            target,
            input_text=input_text,
            purge_directory_names=RUNTIME_PURGE_DIRECTORY_NAMES,
            purge_patterns=RUNTIME_PURGE_PATTERNS,
        )
        case_ops.validate_case_references(target)
    except case_ops.CaseError as exc:
        raise first_linear_recipe.Issue45FirstLinearError(
            f"case staging failed: {exc}"
        ) from exc


def _prepare_case(exe: Path, results_root: str | None) -> dict[str, Any]:
    base_case, base_text, radial_span = _base_case_context()
    base_c0, closure_meta = closure_basis.build_constrained_quasisteady_input(
        base_text,
        radial_span=radial_span,
        macro_avg=TARGET,
        runtime_observability=True,
    )
    text, instrumentation = instrument_first_linear(base_c0)
    p1 = audit_first_linear_structure(base_c0, text)
    root = _evidence_root(
        exe=exe,
        results_root=results_root,
        stem="issue45_first_linear_diagnostic",
    )
    case_dir = root / "case"
    _stage_case(base_case, case_dir, text)
    return {
        "root": root,
        "case_dir": case_dir,
        "input_path": case_dir / "input.i",
        "p1": p1,
        "closure_basis": closure_meta,
        "instrumentation": instrumentation,
    }


def _run_p2(exe: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    log = prepared["root"] / "p2_check_input.log"
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=log,
        extra_args=("--check-input", "--color", "off"),
        stream=False,
    )
    return {
        "status": "PASS" if run.returncode == 0 else "HOLD",
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log),
        "identity": {
            **evidence.identity_record(
                executable=exe,
                input_path=prepared["input_path"],
            ),
            "qpx_sha256": evidence.sha256_file(exe),
        },
    }


def _preflight(
    qpx: str | None,
    results_root: str | None,
) -> tuple[Path, dict[str, Any], dict[str, Any], str]:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    prepared = _prepare_case(exe, results_root)
    p1_pass = prepared["p1"]["status"] == "PASS"
    p2 = _run_p2(exe, prepared) if p1_pass else {}
    status = "PASS" if p1_pass and p2.get("status") == "PASS" else "HOLD"
    return exe, prepared, p2, status


def _write_summary(
    prepared: dict[str, Any],
    p2: dict[str, Any],
    status: str,
    *,
    p3: dict[str, Any] | None = None,
) -> Path:
    path = prepared["root"] / "summary.json"
    payload: dict[str, Any] = {
        "issue": ISSUE,
        "mode": "first-linear-diagnostic" if p3 is not None else "first-linear-preflight",
        "status": p3["decision"]["status"] if p3 is not None else status,
        "p3_executed": p3 is not None,
        "p3_authorized_by_harness": False,
        "target": TARGET,
        "closure_basis": prepared.get("closure_basis"),
        "instrumentation": prepared["instrumentation"],
        "p1": prepared["p1"],
        "p2": p2,
    }
    if p3 is None:
        payload["decision"] = {
            "status": status,
            "class": (
                "FIRST_LINEAR_DIAGNOSTIC_READY"
                if status == "PASS"
                else "HARNESS_OR_CONSTRUCTION_FAIL"
            ),
            "reason": (
                "C0 physics/closure is preserved and user-local QPX accepts the bounded Jacobian/KSP/true-residual diagnostic"
                if status == "PASS"
                else "the first-linear diagnostic did not pass all P0/P1/P2 gates"
            ),
        }
    else:
        payload.update(p3)
    artifacts.write_json_bundle(path.parent, {"summary": (path.name, payload)})
    return path


def run_preflight(qpx: str | None, results_root: str | None) -> int:
    _, prepared, p2, status = _preflight(qpx, results_root)
    path = _write_summary(prepared, p2, status)
    print(f"ISSUE45_FIRST_LINEAR_P1: {prepared['p1']['status']}")
    print(f"ISSUE45_FIRST_LINEAR_P2: {p2.get('status', 'HOLD')}")
    print(f"ISSUE45_FIRST_LINEAR_PREFLIGHT: {status}")
    print(
        "ISSUE45_FIRST_LINEAR_CLASS: "
        + (
            "FIRST_LINEAR_DIAGNOSTIC_READY"
            if status == "PASS"
            else "HARNESS_OR_CONSTRUCTION_FAIL"
        )
    )
    print(f"ISSUE45_FIRST_LINEAR_SUMMARY: {path}")
    return 0 if status == "PASS" else 2


def run_diagnostic(qpx: str | None, results_root: str | None) -> int:
    exe, prepared, p2, status = _preflight(qpx, results_root)
    if status != "PASS":
        path = _write_summary(prepared, p2, status)
        print("ISSUE45_FIRST_LINEAR_PREFLIGHT: HOLD")
        print("ISSUE45_FIRST_LINEAR_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"ISSUE45_FIRST_LINEAR_SUMMARY: {path}")
        return 2

    print("ISSUE45_FIRST_LINEAR_PREFLIGHT: PASS")
    log = prepared["root"] / "p3_first_linear.log"
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=log,
        extra_args=("--color", "off"),
        stream=True,
    )
    print(f"ISSUE45_FIRST_LINEAR_CASE_END: rc={run.returncode}")
    decision = analyze_first_linear_text(
        log.read_text(errors="replace") if log.is_file() else "",
        returncode=run.returncode,
    )
    p3 = {
        "evr_count_for_this_batch": 1,
        "scope": "one bounded C0 initial-state first-linear discriminator",
        "runtime": {
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "log": str(log),
            "identity": {
                **evidence.identity_record(
                    executable=exe,
                    input_path=prepared["input_path"],
                ),
                "qpx_sha256": evidence.sha256_file(exe),
            },
        },
        "decision": decision,
    }
    path = _write_summary(prepared, p2, status, p3=p3)
    jacobian = decision.get("jacobian", {}).get("status", "HOLD")
    identity = decision.get("ksp_identity", {})
    true_rows = decision.get("true_residuals") or []
    print(f"ISSUE45_FIRST_LINEAR_JACOBIAN: {jacobian}")
    print(
        "ISSUE45_FIRST_LINEAR_KSP_IDENTITY: "
        + (
            "PASS"
            if identity.get("ksp_type") and identity.get("pc_type")
            else "HOLD"
        )
    )
    if identity:
        print(
            "ISSUE45_FIRST_LINEAR_KSP: "
            f"type={identity.get('ksp_type')} "
            f"restart={identity.get('restart')} "
            f"pc={identity.get('pc_type')}"
        )
    print("ISSUE45_FIRST_LINEAR_TRUE_RESIDUAL: " + ("PASS" if true_rows else "HOLD"))
    print(f"ISSUE45_FIRST_LINEAR_PRECLASS: {decision['status']}")
    print(f"ISSUE45_FIRST_LINEAR_CLASS: {decision['class']}")
    print(f"ISSUE45_FIRST_LINEAR_REASON: {decision['reason']}")
    print(f"ISSUE45_FIRST_LINEAR_LOG: {log}")
    print(f"ISSUE45_FIRST_LINEAR_SUMMARY: {path}")
    return 0 if decision["status"] == "PASS" else 2
