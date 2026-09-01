"""Issue44 preflight/runtime execution owner for Issue43 fast-plasma output evidence."""
from __future__ import annotations

from . import issue43_fast_output_analysis as _analysis
for _name in dir(_analysis):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_analysis, _name)


def _run_output_preflight(*, qpx: str | None, results_root: str | None) -> int:
    exe = resolve_executable(qpx)
    validate_executable(exe)

    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / issue43_runtime.BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise SystemExit(f"missing accepted qvt electron control: {base_case}")

    mesh = scale_audit.mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()
    input_text = _build_feedback_v5(
        base_text,
        dt=issue43_runtime.DT_FEEDBACK_SMALL,
        steps=issue43_runtime.N_STEPS,
        radial_span=radial_span,
    )
    preflight.validate_parser_symbols_text(input_text)

    report = ooc.observation_report(
        input_text, required_time_separation=issue43_runtime.DT_FEEDBACK_SMALL
    )
    static_decision = ooc.evaluate_observation_report(report)
    if static_decision["status"] != "PASS":
        print("ISSUE44_OUTPUT_PREFLIGHT_P1: HOLD")
        print("ISSUE44_OUTPUT_PREFLIGHT_REASON: static output contract failed")
        return 2

    evidence_root = (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    root = evidence.ensure_fresh_directory(
        evidence_root / f"issue44_output_preflight_{evidence.utc_timestamp()}"
    )
    case_dir = root / "case"
    _stage_case(base_case, case_dir, input_text)
    _validate_assets(case_dir)

    input_path = case_dir / "input.i"
    check_log_path = root / "p2_check_input.log"
    introspection_log_path = root / "p2_output_introspection.log"
    summary_path = root / "summary.json"

    p2 = run_qpx(
        exe,
        cwd=case_dir,
        input_name=input_path.name,
        log_path=check_log_path,
        extra_args=_p2_check_input_args(),
        stream=False,
    )
    p2_failure = _classify_p2_failure(check_log_path, p2.returncode)

    introspection = None
    if p2.returncode == 0:
        introspection = run_qpx(
            exe,
            cwd=case_dir,
            input_name=input_path.name,
            log_path=introspection_log_path,
            extra_args=_p2_output_introspection_args(),
            stream=False,
        )

    framework_evidence = _framework_output_evidence(
        introspection_log_path,
        report,
        check_input_returncode=p2.returncode,
        introspection_returncode=(
            introspection.returncode if introspection is not None else None
        ),
    )
    p3_executed = bool(framework_evidence.get("positive_time_steps"))

    status = (
        "PASS"
        if p2.returncode == 0
        and introspection is not None
        and introspection.returncode == 0
        and framework_evidence["status"] == "PASS"
        and not p3_executed
        else "HOLD"
    )
    summary = {
        "issue": 44,
        "mode": "output-preflight",
        "status": status,
        "p3_executed": p3_executed,
        "identity": {
            **evidence.identity_record(executable=exe, input_path=input_path),
            "qpx_sha256": evidence.sha256_file(exe),
        },
        "p1_output_contract": {"report": report, "decision": static_decision},
        "p2_qpx_introspection": {
            "check_input": {
                "returncode": p2.returncode,
                "wall_seconds": p2.wall_seconds,
                "log": str(check_log_path),
                "failure": p2_failure,
            },
            "output_introspection": {
                "returncode": introspection.returncode if introspection is not None else None,
                "wall_seconds": introspection.wall_seconds if introspection is not None else None,
                "log": str(introspection_log_path),
                "args": list(_p2_output_introspection_args()),
            },
            "framework_evidence": framework_evidence,
        },
    }
    _write_json(summary_path, summary)

    print(f"ISSUE44_OUTPUT_PREFLIGHT_P1: {static_decision['status']}")
    print(
        "ISSUE44_OUTPUT_PREFLIGHT_P2_CHECK_INPUT: "
        + ("PASS" if p2.returncode == 0 else "FAIL")
    )
    if p2.returncode != 0:
        print(f"ISSUE44_OUTPUT_PREFLIGHT_P2_CLASS: {p2_failure['class']}")
        print(f"ISSUE44_OUTPUT_PREFLIGHT_P2_REASON: {p2_failure['reason']}")
        if p2_failure["detail"]:
            print(f"ISSUE44_OUTPUT_PREFLIGHT_P2_DETAIL: {p2_failure['detail']}")
    print(
        "ISSUE44_OUTPUT_PREFLIGHT_P2_OUTPUT_INTROSPECTION: "
        + (
            "PASS"
            if introspection is not None and introspection.returncode == 0
            else "HOLD"
        )
    )
    print(
        "ISSUE44_OUTPUT_PREFLIGHT_FRAMEWORK_EVIDENCE: "
        f"{framework_evidence['status']}"
    )
    if framework_evidence["status"] != "PASS":
        for blocker in framework_evidence.get("blockers", []):
            print(
                "ISSUE44_OUTPUT_PREFLIGHT_FRAMEWORK_BLOCKER: "
                f"{blocker['id']} observed={blocker.get('observed')!r} "
                f"required={blocker.get('required')!r}"
            )
    print(f"ISSUE44_OUTPUT_PREFLIGHT_PRECLASS: {status}")
    print(f"ISSUE44_OUTPUT_PREFLIGHT_CHECK_LOG: {check_log_path}")
    print(f"ISSUE44_OUTPUT_PREFLIGHT_LOG: {introspection_log_path}")
    print(f"ISSUE44_OUTPUT_PREFLIGHT_SUMMARY: {summary_path}")
    return 0 if status == "PASS" else 2


def _run_output_runtime_confirmation(
    *, qpx: str | None, results_root: str | None
) -> int:
    preflight_rc = _run_output_preflight(qpx=qpx, results_root=results_root)
    if preflight_rc != 0:
        print("ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_PRECHECK: HOLD")
        print("ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_CLASS: PREFLIGHT_NOT_PASS")
        return 2
    print("ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_PRECHECK: PASS")

    exe = resolve_executable(qpx)
    validate_executable(exe)
    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / issue43_runtime.BASE_CASE_RELATIVE
    mesh = scale_audit.mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()
    input_text = _build_feedback_v5(
        base_text,
        dt=issue43_runtime.DT_FEEDBACK_SMALL,
        steps=issue43_runtime.N_STEPS,
        radial_span=radial_span,
    )
    preflight.validate_parser_symbols_text(input_text)
    report = ooc.observation_report(
        input_text, required_time_separation=issue43_runtime.DT_FEEDBACK_SMALL
    )

    evidence_root = (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    root = evidence.ensure_fresh_directory(
        evidence_root / f"issue44_output_runtime_{evidence.utc_timestamp()}"
    )
    case_dir = root / "case"
    _stage_case(base_case, case_dir, input_text)
    _validate_assets(case_dir)
    input_path = case_dir / "input.i"
    log_path = root / "p3_runtime.log"
    summary_path = root / "summary.json"

    runtime = run_qpx(
        exe,
        cwd=case_dir,
        input_name=input_path.name,
        log_path=log_path,
        extra_args=("--color", "off"),
        stream=False,
    )
    trajectory = _solver_trajectory(log_path)
    csv_path, csv_times, csv_error = _runtime_csv_times(case_dir)
    decision = _evaluate_output_runtime_confirmation(
        returncode=runtime.returncode,
        trajectory=trajectory,
        csv_times=csv_times,
        dt=issue43_runtime.DT_FEEDBACK_SMALL,
        steps=issue43_runtime.N_STEPS,
        row_tolerance=float(report["csv"]["new_row_tolerance"]),
    )

    summary = {
        "issue": 44,
        "mode": "output-runtime-confirmation",
        "status": decision["status"],
        "class": decision["class"],
        "scope": (
            "observation-contract confirmation only; no Issue43 relaxation, "
            "quasi-steady, or production-timestep classification"
        ),
        "p3_executed": True,
        "preflight_passed": True,
        "identity": {
            **evidence.identity_record(executable=exe, input_path=input_path),
            "qpx_sha256": evidence.sha256_file(exe),
        },
        "output_contract": report,
        "runtime": {
            "returncode": runtime.returncode,
            "wall_seconds": runtime.wall_seconds,
            "log": str(log_path),
            "solver_trajectory": trajectory,
        },
        "csv": {
            "path": str(csv_path) if csv_path is not None else None,
            "times": csv_times,
            "error": csv_error,
        },
        "decision": decision,
    }
    _write_json(summary_path, summary)

    print(
        "ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_SOLVER: "
        + ("PASS" if decision["solver_complete"] else "HOLD")
    )
    observation_pass = all(
        item["status"] == "PASS" for item in decision["observation_checks"]
    )
    print(
        "ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_CSV_ROWS: "
        + ("PASS" if observation_pass else "HOLD")
    )
    if decision["status"] != "PASS":
        for check in decision["solver_checks"] + decision["observation_checks"]:
            if check["status"] != "PASS":
                print(
                    "ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_BLOCKER: "
                    f"{check['id']} observed={check.get('observed')!r} "
                    f"required={check.get('required')!r}"
                )
        if csv_error:
            print(f"ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_CSV_ERROR: {csv_error}")
    print(f"ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_PRECLASS: {decision['status']}")
    print(f"ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_CLASS: {decision['class']}")
    print(f"ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_LOG: {log_path}")
    print(f"ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_SUMMARY: {summary_path}")
    return 0 if decision["status"] == "PASS" else 2


__all__ = [name for name in globals() if not name.startswith("__")]
