"""Run the one-queue FV internal completion campaign for the R3 electron blocker."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from experiments.Issue93_r3_electron_isolation.operator_decomposition import _check_accepted_qvt_csv
from experiments.Issue93_r3_electron_isolation.prepare import ELECTRON_REFERENCE_CASE
from experiments.Issue93_r3_electron_isolation.run import _electron_residuals
from experiments.R3_electron_master_diagnostic.execution_status import solver_status
from qpx_harness.diagnose import diagnose_jacobian_evidence
from qpx_harness.evidence import (
    AttributionSignals,
    ErrorLedger,
    classify_attribution,
    create_collision_safe_directory,
    extract_jacobian_evidence,
    failure_signature,
    runtime_core_facts,
    sha256_file,
    utc_timestamp,
    write_json_bundle,
)
from qpx_harness.execution.runtime import resolve_executable, run_qpx, validate_executable

from .cases import stage_completion_case
from .classify import classify_completion
from .face_interpolation_audit import audit_constant_face_interpolation
from .rz_decomposition import decompose_rz_constant_state
from .spec import CASES, CASE_BY_ID, JACOBIAN_CASE_IDS, CompletionCaseSpec

EXPERIMENT_ID = "r3-fv-internal-completion"


def _record_event(
    ledger: ErrorLedger,
    *,
    run_id: str,
    stage: str,
    case_id: str | None,
    code: str,
    message: str,
    source_layer: str,
    signals: AttributionSignals,
    evidence: dict[str, Any] | None = None,
) -> None:
    ledger.record(
        run_id=run_id,
        issue=98,
        stage=stage,
        case_id=case_id,
        error_code=code,
        message=message,
        source_layer=source_layer,
        attribution=classify_attribution(signals),
        evidence=evidence or {},
        signature=f"{stage}:{case_id or 'campaign'}:{code}",
    )


def _last_scalar_csv(case_dir: Path) -> Path | None:
    direct = case_dir / "input_out.csv"
    if direct.is_file():
        return direct
    matches = sorted(case_dir.glob("input_out*.csv"))
    return matches[-1] if matches else None


def _accepted_checker(case_dir: Path) -> dict[str, Any]:
    csv_path = _last_scalar_csv(case_dir)
    if csv_path is None:
        return {"pass": False, "error": "missing scalar CSV"}
    try:
        return _check_accepted_qvt_csv(csv_path, case_dir / "expected.json")
    except Exception as exc:
        return {"pass": False, "error": str(exc)}


def _p2_case(exe: Path, case_dir: Path, log: Path, timeout: float) -> dict[str, Any]:
    result = run_qpx(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=("--check-input",),
        timeout_seconds=timeout,
    )
    text = log.read_text(errors="replace")
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "log": str(log),
        "log_tail": text[-12000:],
    }


def _run_solve_case(exe: Path, spec: CompletionCaseSpec, case_dir: Path, log: Path, timeout: float) -> dict[str, Any]:
    result = run_qpx(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=(
            "Executioner/num_steps=1",
            "-snes_monitor",
            "-snes_converged_reason",
            "-ksp_converged_reason",
        ),
        timeout_seconds=timeout,
    )
    text = log.read_text(errors="replace")
    checker = _accepted_checker(case_dir)
    failure = failure_signature(text)
    facts = runtime_core_facts(text, returncode=result.returncode, coupled_scaling_variables=("n_e",))
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "log": str(log),
        "failure_signature": failure,
        "runtime_facts": facts,
        "electron_residuals": _electron_residuals(text),
        "checker": checker,
        "solver_status": solver_status(
            returncode=result.returncode,
            timed_out=result.timed_out,
            failure=failure,
            checker=checker,
        ),
        "passed": result.returncode == 0 and checker.get("pass") is True,
        "operator": spec.operator,
    }


def _gradient_csv(case_dir: Path) -> Path | None:
    matches = sorted(case_dir.glob("*gradient_samples*.csv"))
    if matches:
        return matches[-1]
    matches = sorted(case_dir.glob("*.csv"))
    for path in matches:
        try:
            header = path.read_text(errors="replace").splitlines()[0]
        except (IndexError, OSError):
            continue
        if "grad_ad_x" in header and "grad_real_x" in header:
            return path
    return None


def _float(row: dict[str, str], key: str) -> float | None:
    raw = row.get(key)
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _centroid_key(x: float, y: float) -> tuple[float, float]:
    return round(x, 12), round(y, 12)


def _gradient_metrics(case_dir: Path, interior_centroids: set[tuple[float, float]]) -> dict[str, Any]:
    path = _gradient_csv(case_dir)
    if path is None:
        return {"status": "MISSING_CSV", "csv": None}
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    parsed: list[dict[str, Any]] = []
    for row in rows:
        ad_x = _float(row, "grad_ad_x")
        ad_y = _float(row, "grad_ad_y")
        real_x = _float(row, "grad_real_x")
        real_y = _float(row, "grad_real_y")
        x = _float(row, "x")
        y = _float(row, "y")
        if None in (ad_x, ad_y, real_x, real_y):
            continue
        ad_norm = math.hypot(float(ad_x), float(ad_y))
        real_norm = math.hypot(float(real_x), float(real_y))
        is_interior = bool(
            x is not None and y is not None and _centroid_key(float(x), float(y)) in interior_centroids
        )
        parsed.append(
            {
                "id": row.get("id") or row.get("elem_id") or row.get("element_id"),
                "x": x,
                "y": y,
                "grad_ad_x": ad_x,
                "grad_ad_y": ad_y,
                "grad_real_x": real_x,
                "grad_real_y": real_y,
                "ad_norm": ad_norm,
                "real_norm": real_norm,
                "ad_real_norm_diff": abs(ad_norm - real_norm),
                "interior": is_interior,
            }
        )
    if not parsed:
        return {"status": "NO_VALID_ROWS", "csv": str(path), "rows": []}
    interior = [row for row in parsed if row["interior"]]
    return {
        "status": "PASS",
        "csv": str(path),
        "row_count": len(parsed),
        "interior_row_count": len(interior),
        "ad_max": max(float(row["ad_norm"]) for row in parsed),
        "real_max": max(float(row["real_norm"]) for row in parsed),
        "ad_real_max_diff": max(float(row["ad_real_norm_diff"]) for row in parsed),
        "ad_interior_max": max((float(row["ad_norm"]) for row in interior), default=None),
        "real_interior_max": max((float(row["real_norm"]) for row in interior), default=None),
        "rows": parsed,
    }


def _run_gradient_case(
    exe: Path,
    case_dir: Path,
    log: Path,
    timeout: float,
    interior_centroids: set[tuple[float, float]],
) -> dict[str, Any]:
    result = run_qpx(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=(),
        timeout_seconds=timeout,
    )
    text = log.read_text(errors="replace")
    metrics = _gradient_metrics(case_dir, interior_centroids)
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "log": str(log),
        "failure_signature": failure_signature(text),
        "solver_status": "NO_SOLVE_MEASUREMENT" if result.returncode == 0 else "RUNTIME_FAIL",
        "passed": result.returncode == 0 and metrics.get("status") == "PASS",
        "gradient": metrics,
    }


def _jacobian_case(
    exe: Path,
    spec: CompletionCaseSpec,
    target: Path,
    log: Path,
    timeout: float,
    tolerance: float,
) -> dict[str, Any]:
    stage_completion_case(spec, target)
    result = run_qpx(
        exe,
        cwd=target,
        input_name="input.i",
        log_path=log,
        extra_args=(
            "Executioner/num_steps=1",
            "Executioner/abort_on_solve_fail=true",
            "-snes_test_jacobian",
        ),
        timeout_seconds=timeout,
    )
    text = log.read_text(errors="replace")
    comparison = diagnose_jacobian_evidence(
        extract_jacobian_evidence(text),
        relative_tolerance=tolerance,
    )
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "log": str(log),
        "comparison": comparison,
        "status": "PASS" if comparison.get("status") == "PASS" else "HOLD",
    }


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    results_root = args.results_root.resolve() if args.results_root else exe.parent / "temp" / "results"
    results_root.mkdir(parents=True, exist_ok=True)
    root = create_collision_safe_directory(results_root, f"r3_fv_completion_{utc_timestamp()}")
    run_id = root.name
    ledger = ErrorLedger.for_run(root, persistent_path=args.error_ledger)
    cases_root = root / "cases"
    logs_root = root / "logs"
    jac_root = root / "jacobian"
    cases_root.mkdir(); logs_root.mkdir(); jac_root.mkdir()

    mesh_path = ELECTRON_REFERENCE_CASE / "qvt.msh"
    rz: dict[str, Any] = {}
    try:
        rz["N1"] = decompose_rz_constant_state(mesh_path, n0=1.0)
        rz["N1E16"] = decompose_rz_constant_state(mesh_path, n0=1.0e16)
    except Exception as exc:
        rz["error"] = str(exc)
        _record_event(
            ledger,
            run_id=run_id,
            stage="OFFLINE_RZ",
            case_id=None,
            code="RZ_DECOMPOSITION_FAIL",
            message=str(exc),
            source_layer="completion_offline_reproducer",
            signals=AttributionSignals(assistant_generated_contract_violation=True),
        )

    face_interpolation: dict[str, Any] = {}
    try:
        face_interpolation["N1"] = audit_constant_face_interpolation(mesh_path, n0=1.0)
        face_interpolation["N1E16"] = audit_constant_face_interpolation(mesh_path, n0=1.0e16)
    except Exception as exc:
        face_interpolation["error"] = str(exc)
        _record_event(
            ledger,
            run_id=run_id,
            stage="OFFLINE_FACE_INTERPOLATION",
            case_id=None,
            code="FACE_INTERPOLATION_AUDIT_FAIL",
            message=str(exc),
            source_layer="completion_offline_face_interpolation_audit",
            signals=AttributionSignals(assistant_generated_contract_violation=True),
        )

    interior_centroids: set[tuple[float, float]] = set()
    for row in rz.get("N1E16", {}).get("rows", []):
        centroid = row.get("centroid")
        if isinstance(centroid, list) and len(centroid) >= 2:
            interior_centroids.add(_centroid_key(float(centroid[0]), float(centroid[1])))

    identity = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "qpx_realpath": str(exe),
        "qpx_sha256": sha256_file(exe),
        "electron_reference_case": str(ELECTRON_REFERENCE_CASE),
        "mesh": str(mesh_path),
        "geometry": "HELD_FIXED_OUT_OF_SCOPE",
        "case_ids": [case.case_id for case in CASES],
        "jacobian_case_ids": list(JACOBIAN_CASE_IDS),
        "one_queue_contract": "all remaining FV internal discriminators and Jacobian probes are predeclared before QPX execution",
    }
    write_json_bundle(
        root,
        {
            "identity": ("identity.json", identity),
            "rz": ("rz_decomposition.json", rz),
            "face_interpolation": ("face_interpolation_audit.json", face_interpolation),
        },
    )

    cases: dict[str, dict[str, Any]] = {}
    for spec in CASES:
        target = cases_root / spec.case_id
        try:
            staged = stage_completion_case(spec, target)
            cases[spec.case_id] = {
                "spec": {
                    "mode": spec.mode,
                    "operator": spec.operator,
                    "n0": spec.n0,
                    "two_term_boundary_expansion": spec.two_term_boundary_expansion,
                    "nl_abs_tol": spec.nl_abs_tol,
                    "meaning": spec.meaning,
                },
                "stage": staged,
                "status": "STAGED",
                "passed": False,
            }
        except Exception as exc:
            cases[spec.case_id] = {
                "spec": {"mode": spec.mode, "operator": spec.operator, "meaning": spec.meaning},
                "status": "CONSTRUCTION_FAIL",
                "passed": False,
                "error": str(exc),
            }
            _record_event(
                ledger,
                run_id=run_id,
                stage="P1",
                case_id=spec.case_id,
                code="COMPLETION_CASE_CONSTRUCTION_FAIL",
                message=str(exc),
                source_layer="completion_case_builder",
                signals=AttributionSignals(assistant_generated_contract_violation=True),
            )

    for spec in CASES:
        case = cases[spec.case_id]
        if case["status"] != "STAGED":
            continue
        p2 = _p2_case(exe, cases_root / spec.case_id, logs_root / f"{spec.case_id}_p2.log", args.timeout)
        case["p2"] = p2
        if p2["returncode"] == 0 and not p2["timed_out"]:
            case["status"] = "P2_PASS"
        else:
            case["status"] = "P2_FAIL"
            _record_event(
                ledger,
                run_id=run_id,
                stage="P2",
                case_id=spec.case_id,
                code="COMPLETION_CASE_P2_FAIL",
                message="completion case failed --check-input; independent cases continue",
                source_layer="framework_or_generated_input",
                signals=AttributionSignals(),
                evidence=p2,
            )

    gradients: dict[str, Any] = {}
    for spec in CASES:
        case = cases[spec.case_id]
        if case["status"] != "P2_PASS":
            continue
        case_dir = cases_root / spec.case_id
        log = logs_root / f"{spec.case_id}_p3.log"
        if spec.mode == "gradient":
            result = _run_gradient_case(exe, case_dir, log, args.timeout, interior_centroids)
            gradients[spec.case_id] = result.get("gradient", {})
        else:
            result = _run_solve_case(exe, spec, case_dir, log, args.timeout)
        case.update(result)
        case["status"] = "PASS" if result.get("passed") else "FAIL"

    jacobians: dict[str, Any] = {}
    for case_id in JACOBIAN_CASE_IDS:
        spec = CASE_BY_ID[case_id]
        if cases.get(case_id, {}).get("p2", {}).get("returncode") != 0:
            jacobians[case_id] = {"status": "NOT_RUN_P2_FAIL"}
            continue
        try:
            jacobians[case_id] = _jacobian_case(
                exe,
                spec,
                jac_root / case_id,
                jac_root / f"{case_id}.log",
                args.jacobian_timeout,
                args.jacobian_tolerance,
            )
        except Exception as exc:
            jacobians[case_id] = {"status": "HOLD", "error": str(exc)}
            _record_event(
                ledger,
                run_id=run_id,
                stage="JACOBIAN",
                case_id=case_id,
                code="COMPLETION_JACOBIAN_PROBE_FAIL",
                message=str(exc),
                source_layer="completion_jacobian_probe",
                signals=AttributionSignals(),
            )

    diagnosis = classify_completion(cases, gradients, rz, jacobians)
    primary = diagnosis.get("primary_owner")
    if isinstance(primary, dict) and diagnosis.get("status") == "ISOLATED":
        _record_event(
            ledger,
            run_id=run_id,
            stage="DECISION",
            case_id=None,
            code=f"ATOMIC_OWNER_{primary['owner']}",
            message=str(primary.get("mechanism", primary["owner"])),
            source_layer="scientific_fault_isolation",
            signals=AttributionSignals(
                contract_conformant=True,
                reproducible_runtime_failure=True,
                isolated_code_owner=str(primary["owner"]),
            ),
            evidence={"evidence": primary.get("evidence", []), "geometry": diagnosis.get("geometry")},
        )

    paths = write_json_bundle(
        root,
        {
            "case_matrix": ("case_matrix.json", cases),
            "gradient_matrix": ("gradient_matrix.json", gradients),
            "jacobian_matrix": ("jacobian_matrix.json", jacobians),
            "final_diagnosis": ("final_diagnosis.json", diagnosis),
        },
    )
    error_paths = ledger.write_summaries(root)
    summary = {
        "status": diagnosis.get("status"),
        "run_id": run_id,
        "root": str(root),
        "primary_owner": diagnosis.get("primary_owner"),
        "secondary_candidates": diagnosis.get("secondary_candidates", []),
        "unresolved": diagnosis.get("unresolved", []),
        "geometry": diagnosis.get("geometry"),
        "artifacts": paths,
        "error_stats": error_paths,
    }
    write_json_bundle(root, {"summary": ("summary.json", summary)})

    print(f"R3_FV_COMPLETION_ROOT: {root}")
    print(f"R3_FV_COMPLETION_STATUS: {diagnosis.get('status')}")
    print("R3_FV_COMPLETION_PRIMARY_OWNER: " + json.dumps(diagnosis.get("primary_owner")))
    print(f"R3_FV_COMPLETION_SUMMARY: {root / 'summary.json'}")
    return 0 if diagnosis.get("status") in {"ISOLATED", "OPERATOR_PASS"} else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qpx")
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--error-ledger", type=Path)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--jacobian-timeout", type=float, default=300.0)
    parser.add_argument("--jacobian-tolerance", type=float, default=1.0e-8)
    args = parser.parse_args()
    if args.timeout <= 0 or args.jacobian_timeout <= 0:
        parser.error("timeouts must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())