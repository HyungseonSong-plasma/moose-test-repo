"""P0/P1/P2/P3 orchestration owner for Issue43 coupling diagnostics."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import artifacts
from .. import evidence
from .. import issue43_fast_relaxation as v5
from ..runtime import resolve_executable, run_qpx, validate_executable
from ..scale_audit import mesh_stats
from .analysis import analyze_jacobian_log, analyze_log
from .constants import (
    BASE_CASE_RELATIVE,
    DT_CONTROL,
    DT_FAIL,
    JACOBIAN_REL_TOL,
    FastPlasmaCouplingDiagnosticError,
)
from .structure import _build_case, _p1_case, _stage_case


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    artifacts.write_json_bundle(path.parent, {"summary": (path.name, payload)})


def _prepare_cases(
    *, exe: Path, results_root: str | None, jacobian_test: bool = False
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    base_case = repo_root / BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise FastPlasmaCouplingDiagnosticError(
            f"missing accepted qvt electron control: {base_case}"
        )

    mesh = mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()
    variants = {
        "T1_dt1e14": _build_case(
            base_text,
            dt=DT_CONTROL,
            radial_span=radial_span,
            jacobian_test=jacobian_test,
        ),
        "T2_dt1e13": _build_case(
            base_text,
            dt=DT_FAIL,
            radial_span=radial_span,
            jacobian_test=jacobian_test,
        ),
    }

    p1 = {
        label: _p1_case(
            label,
            text,
            dt=float(meta["dt"]),
            jacobian_test=jacobian_test,
        )
        for label, (text, meta) in variants.items()
    }
    p1_status = "PASS" if all(item["status"] == "PASS" for item in p1.values()) else "HOLD"

    evidence_root = (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    stem = "issue43_jacobian_diagnostic" if jacobian_test else "issue43_coupling_diagnostic"
    root = evidence.ensure_fresh_directory(
        evidence_root / f"{stem}_{evidence.utc_timestamp()}"
    )
    cases_root = root / "cases"
    cases_root.mkdir()

    cases: dict[str, Any] = {}
    for label, (text, meta) in variants.items():
        case_dir = cases_root / label
        _stage_case(base_case, case_dir, text)
        cases[label] = {
            "case_dir": case_dir,
            "input_path": case_dir / "input.i",
            "meta": meta,
            "p1": p1[label],
        }

    return {
        "root": root,
        "cases": cases,
        "p1": p1,
        "p1_status": p1_status,
        "jacobian_test": jacobian_test,
    }


def _run_p2(*, exe: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    p2: dict[str, Any] = {}
    for label, case in prepared["cases"].items():
        log_path = prepared["root"] / f"p2_{label}.log"
        run = run_qpx(
            exe,
            cwd=case["case_dir"],
            input_name="input.i",
            log_path=log_path,
            extra_args=("--check-input", "--color", "off"),
            stream=False,
        )
        p2[label] = {
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "log": str(log_path),
            "failure": v5._classify_p2_failure(log_path, run.returncode),
            "identity": {
                **evidence.identity_record(executable=exe, input_path=case["input_path"]),
                "qpx_sha256": evidence.sha256_file(exe),
            },
        }
    return p2


def _emit_preflight_markers(
    *,
    prepared: dict[str, Any],
    p2: dict[str, Any],
    status: str,
    summary_path: Path,
    prefix: str = "ISSUE43_COUPLING_DIAGNOSTIC",
) -> None:
    print(f"{prefix}_P1: {prepared['p1_status']}")
    for label in ("T1_dt1e14", "T2_dt1e13"):
        result = p2.get(label)
        if result is None:
            print(f"{prefix}_P2_{label}: HOLD")
            continue
        print(f"{prefix}_P2_{label}: " + ("PASS" if result["returncode"] == 0 else "FAIL"))
        if result["returncode"] != 0:
            failure = result["failure"]
            print(f"{prefix}_P2_{label}_CLASS: {failure.get('class')}")
            print(f"{prefix}_P2_{label}_REASON: {failure.get('reason')}")
            if failure.get("detail"):
                print(f"{prefix}_P2_{label}_DETAIL: {failure['detail']}")
    print(f"{prefix}_PREFLIGHT: {status}")
    print(f"{prefix}_SUMMARY: {summary_path}")


def _preflight_result(
    *, qpx: str | None, results_root: str | None, jacobian_test: bool
) -> tuple[Path, dict[str, Any], dict[str, Any], str]:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    prepared = _prepare_cases(
        exe=exe, results_root=results_root, jacobian_test=jacobian_test
    )
    p2 = (
        _run_p2(exe=exe, prepared=prepared)
        if prepared["p1_status"] == "PASS"
        else {}
    )
    p2_pass = bool(p2) and all(item["returncode"] == 0 for item in p2.values())
    status = "PASS" if prepared["p1_status"] == "PASS" and p2_pass else "HOLD"
    return exe, prepared, p2, status


def run_preflight(
    *, qpx: str | None, results_root: str | None, jacobian_test: bool = False
) -> int:
    _, prepared, p2, status = _preflight_result(
        qpx=qpx, results_root=results_root, jacobian_test=jacobian_test
    )
    summary_path = prepared["root"] / "summary.json"
    mode = "jacobian-diagnostic-preflight" if jacobian_test else "coupling-diagnostic-preflight"
    claim = (
        "construction readiness for PETSc assembled-vs-finite-difference Jacobian comparison on the fixed T1/T2 discriminator"
        if jacobian_test
        else "construction and observability readiness for the dt=1e-14 control vs dt=1e-13 failing coupling discriminator"
    )
    _write_summary(
        summary_path,
        {
            "issue": 43,
            "mode": mode,
            "status": status,
            "p3_executed": False,
            "jacobian_relative_tolerance": JACOBIAN_REL_TOL if jacobian_test else None,
            "claim": claim,
            "p1": prepared["p1"],
            "p2": p2,
        },
    )
    prefix = "ISSUE43_JACOBIAN_DIAGNOSTIC" if jacobian_test else "ISSUE43_COUPLING_DIAGNOSTIC"
    _emit_preflight_markers(
        prepared=prepared,
        p2=p2,
        status=status,
        summary_path=summary_path,
        prefix=prefix,
    )
    return 0 if status == "PASS" else 2


def _run_cases(
    *, exe: Path, prepared: dict[str, Any], jacobian_test: bool
) -> dict[str, Any]:
    runtime: dict[str, Any] = {}
    prefix = "ISSUE43_JACOBIAN_DIAGNOSTIC" if jacobian_test else "ISSUE43_COUPLING_DIAGNOSTIC"
    for label in ("T1_dt1e14", "T2_dt1e13"):
        case = prepared["cases"][label]
        log_path = prepared["root"] / f"p3_{label}.log"
        print(f"{prefix}_CASE_START: {label}")
        run = run_qpx(
            exe,
            cwd=case["case_dir"],
            input_name="input.i",
            log_path=log_path,
            extra_args=("--color", "off"),
            stream=True,
        )
        print(f"{prefix}_CASE_END: {label} rc={run.returncode}")
        item = {
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "log": str(log_path),
            "trajectory": v5._solver_trajectory(log_path),
            "diagnostic": analyze_log(log_path, returncode=run.returncode),
        }
        if jacobian_test:
            item["jacobian"] = analyze_jacobian_log(log_path)
        runtime[label] = item
    return runtime


def run_runtime(*, qpx: str | None, results_root: str | None) -> int:
    exe, prepared, p2, status = _preflight_result(
        qpx=qpx, results_root=results_root, jacobian_test=False
    )
    if status != "PASS":
        summary_path = prepared["root"] / "summary.json"
        _write_summary(
            summary_path,
            {
                "issue": 43,
                "mode": "coupling-diagnostic-runtime",
                "status": "HOLD",
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "p3_executed": False,
                "p1": prepared["p1"],
                "p2": p2,
            },
        )
        _emit_preflight_markers(
            prepared=prepared,
            p2=p2,
            status="HOLD",
            summary_path=summary_path,
        )
        return 2

    print("ISSUE43_COUPLING_DIAGNOSTIC_PREFLIGHT: PASS")
    runtime = _run_cases(exe=exe, prepared=prepared, jacobian_test=False)
    t1 = runtime["T1_dt1e14"]
    t2 = runtime["T2_dt1e13"]
    t1_pass = (
        t1["returncode"] == 0
        and t1["trajectory"].get("time_steps_seen") == 1
        and t1["trajectory"].get("converged_steps", 0) >= 1
    )
    if not t1_pass:
        decision = {
            "status": "HOLD",
            "class": "DIAGNOSTIC_INSUFFICIENT",
            "reason": "diagnostic-only instrumentation did not reproduce the dt=1e-14 advancement control",
        }
    elif t2["returncode"] == 0:
        decision = {
            "status": "HOLD",
            "class": "DIAGNOSTIC_INSUFFICIENT",
            "reason": "historical dt=1e-13 failing branch unexpectedly passed under diagnostic-only instrumentation",
        }
    else:
        diagnostic = t2["diagnostic"]
        decision = {
            "status": "PASS" if diagnostic["class"] != "DIAGNOSTIC_INSUFFICIENT" else "HOLD",
            "class": diagnostic["class"],
            "reason": diagnostic["reason"],
            "pc_failure_reason": diagnostic.get("pc_failure_reason"),
        }

    summary_path = prepared["root"] / "summary.json"
    _write_summary(
        summary_path,
        {
            "issue": 43,
            "mode": "coupling-diagnostic-runtime",
            "status": decision["status"],
            "class": decision["class"],
            "scope": "failure localization only; no timestep tuning, relaxation-time promotion, or production architecture decision",
            "p3_executed": True,
            "p1": prepared["p1"],
            "p2": p2,
            "runtime": runtime,
            "decision": decision,
        },
    )

    print("ISSUE43_COUPLING_DIAGNOSTIC_T1_CONTROL: " + ("PASS" if t1_pass else "HOLD"))
    print(
        "ISSUE43_COUPLING_DIAGNOSTIC_T2_REPRODUCED: "
        + ("PASS" if t2["returncode"] != 0 else "HOLD")
    )
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_PRECLASS: {decision['status']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_CLASS: {decision['class']}")
    if decision.get("pc_failure_reason"):
        print(f"ISSUE43_COUPLING_DIAGNOSTIC_PC_REASON: {decision['pc_failure_reason']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_REASON: {decision['reason']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_T1_LOG: {t1['log']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_T2_LOG: {t2['log']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_SUMMARY: {summary_path}")
    return 0 if decision["status"] == "PASS" else 2


def run_jacobian_runtime(*, qpx: str | None, results_root: str | None) -> int:
    exe, prepared, p2, status = _preflight_result(
        qpx=qpx, results_root=results_root, jacobian_test=True
    )
    prefix = "ISSUE43_JACOBIAN_DIAGNOSTIC"
    if status != "PASS":
        summary_path = prepared["root"] / "summary.json"
        _write_summary(
            summary_path,
            {
                "issue": 43,
                "mode": "jacobian-diagnostic-runtime",
                "status": "HOLD",
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "p3_executed": False,
                "p1": prepared["p1"],
                "p2": p2,
            },
        )
        _emit_preflight_markers(
            prepared=prepared,
            p2=p2,
            status="HOLD",
            summary_path=summary_path,
            prefix=prefix,
        )
        return 2

    print(f"{prefix}_PREFLIGHT: PASS")
    runtime = _run_cases(exe=exe, prepared=prepared, jacobian_test=True)
    t1 = runtime["T1_dt1e14"]
    t2 = runtime["T2_dt1e13"]

    t1_control = (
        t1["returncode"] == 0
        and t1["trajectory"].get("time_steps_seen") == 1
        and t1["trajectory"].get("converged_steps", 0) >= 1
    )
    t2_zero_pivot = (
        t2["returncode"] != 0
        and t2["diagnostic"].get("pc_failure_reason") == "FACTOR_NUMERIC_ZEROPIVOT"
    )
    t1_jacobian_pass = t1["jacobian"].get("status") == "PASS"
    t2_jacobian_pass = t2["jacobian"].get("status") == "PASS"

    if not t1_jacobian_pass or not t2_jacobian_pass:
        classes = {t1["jacobian"].get("class"), t2["jacobian"].get("class")}
        decision_class = (
            "JACOBIAN_MISMATCH"
            if "JACOBIAN_MISMATCH" in classes
            else "JACOBIAN_EVIDENCE_INSUFFICIENT"
        )
        decision = {
            "status": "HOLD",
            "class": decision_class,
            "reason": "at least one T1/T2 Jacobian comparison did not establish assembled-vs-finite-difference agreement",
        }
    elif not t1_control:
        decision = {
            "status": "HOLD",
            "class": "DIAGNOSTIC_INSUFFICIENT",
            "reason": "Jacobian instrumentation did not preserve the dt=1e-14 advancement control",
        }
    elif not t2_zero_pivot:
        decision = {
            "status": "HOLD",
            "class": "DIAGNOSTIC_INSUFFICIENT",
            "reason": "Jacobian instrumentation did not reproduce the dt=1e-13 FACTOR_NUMERIC_ZEROPIVOT signature",
        }
    else:
        decision = {
            "status": "PASS",
            "class": "JACOBIAN_CORRECT_ZERO_PIVOT_REPRODUCED",
            "reason": (
                "both T1/T2 assembled Jacobians agree with PETSc finite differences within the declared tolerance, "
                "while T2 still fails with FACTOR_NUMERIC_ZEROPIVOT"
            ),
        }

    summary_path = prepared["root"] / "summary.json"
    _write_summary(
        summary_path,
        {
            "issue": 43,
            "mode": "jacobian-diagnostic-runtime",
            "status": decision["status"],
            "class": decision["class"],
            "scope": "Jacobian correctness and zero-pivot reproduction only; no solver retuning or production architecture promotion",
            "jacobian_relative_tolerance": JACOBIAN_REL_TOL,
            "p3_executed": True,
            "p1": prepared["p1"],
            "p2": p2,
            "runtime": runtime,
            "decision": decision,
        },
    )

    print(f"{prefix}_T1_CONTROL: " + ("PASS" if t1_control else "HOLD"))
    print(f"{prefix}_T1_JACOBIAN: {t1['jacobian'].get('status')}")
    print(f"{prefix}_T2_JACOBIAN: {t2['jacobian'].get('status')}")
    print(f"{prefix}_T2_NUMERIC_ZERO_PIVOT: " + ("PASS" if t2_zero_pivot else "HOLD"))
    print(f"{prefix}_PRECLASS: {decision['status']}")
    print(f"{prefix}_CLASS: {decision['class']}")
    print(f"{prefix}_REASON: {decision['reason']}")
    print(f"{prefix}_T1_LOG: {t1['log']}")
    print(f"{prefix}_T2_LOG: {t2['log']}")
    print(f"{prefix}_SUMMARY: {summary_path}")
    return 0 if decision["status"] == "PASS" else 2
