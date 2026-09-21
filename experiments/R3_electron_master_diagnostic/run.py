"""One-shot R3 electron diagnostic batch using qpx_harness execution/evidence APIs."""
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
from physics_harness.reasoning.jacobian import diagnose_jacobian_evidence
from physics_harness.adapters.moose.nonlinear_solver import failure_signature, runtime_core_facts
from physics_harness.evidence import (
    AttributionSignals,
    ErrorLedger,
    classify_attribution,
    create_collision_safe_directory,
    extract_jacobian_evidence,
    sha256_file,
    utc_timestamp,
    write_json_bundle,
)
from physics_harness.execution.runtime import resolve_executable, run_physics, validate_executable

from .cases import stage_master_case, stage_r3_proxy_case
from .classify import classify_matrix
from .spec import CHEAP_CASES, FROZEN_DIFFUSION, FROZEN_MOBILITY, CaseSpec

EXPERIMENT_ID = "r3-electron-master-diagnostic"
CASE_BY_ID = {spec.case_id: spec for spec in CHEAP_CASES}


def _last_csv(case_dir: Path) -> Path | None:
    direct = case_dir / "input_out.csv"
    if direct.is_file():
        return direct
    matches = sorted(case_dir.glob("input_out*.csv"))
    return matches[-1] if matches else None


def _read_observables(case_dir: Path) -> dict[str, Any]:
    path = _last_csv(case_dir)
    if path is None:
        return {"csv": None, "last_row": {}}
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = rows[-1] if rows else {}
    parsed: dict[str, Any] = {}
    for key, value in row.items():
        try:
            parsed[key] = float(value) if value not in (None, "") else value
        except (TypeError, ValueError):
            parsed[key] = value
    return {"csv": str(path), "last_row": parsed}


def _coefficient_contract(observables: dict[str, Any]) -> bool | None:
    row = observables.get("last_row", {})
    keys = ("diag_electron_diffusion_min", "diag_electron_diffusion_max")
    if not all(isinstance(row.get(key), (int, float)) for key in keys):
        return None
    lo, hi = float(row[keys[0]]), float(row[keys[1]])
    return (
        math.isclose(lo, FROZEN_DIFFUSION, rel_tol=1.0e-10, abs_tol=0.0)
        and math.isclose(hi, FROZEN_DIFFUSION, rel_tol=1.0e-10, abs_tol=0.0)
        and math.isclose(lo, hi, rel_tol=1.0e-13, abs_tol=0.0)
    )


def _checker(case_dir: Path) -> dict[str, Any]:
    try:
        return _check_accepted_qvt_csv(case_dir / "input_out.csv", case_dir / "expected.json")
    except Exception as exc:
        return {"pass": False, "error": str(exc)}


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
    remedy: str | None = None,
) -> None:
    ledger.record(
        run_id=run_id,
        issue=94,
        stage=stage,
        case_id=case_id,
        error_code=code,
        message=message,
        source_layer=source_layer,
        attribution=classify_attribution(signals),
        evidence=evidence or {},
        remedy=remedy,
        signature=f"{stage}:{case_id or 'campaign'}:{code}",
    )


def _p2_case(*, exe: Path, case_dir: Path, log: Path, timeout: float | None) -> dict[str, Any]:
    result = run_physics(
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


def _p3_case(*, exe: Path, case_dir: Path, log: Path, timeout: float | None) -> dict[str, Any]:
    result = run_physics(
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
    checker = _checker(case_dir)
    observables = _read_observables(case_dir)
    facts = runtime_core_facts(text, returncode=result.returncode, coupled_scaling_variables=("n_e",))
    passed = result.returncode == 0 and checker.get("pass") is True
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "log": str(log),
        "failure_signature": failure_signature(text),
        "electron_residuals": _electron_residuals(text),
        "runtime_facts": facts,
        "checker": checker,
        "observables": observables,
        "coefficient_contract_pass": _coefficient_contract(observables),
        "passed": passed,
    }


def _jacobian_case(
    *,
    spec: CaseSpec,
    root: Path,
    exe: Path,
    timeout: float | None,
    relative_tolerance: float,
) -> dict[str, Any]:
    case_dir = root / spec.case_id
    stage_master_case(spec, case_dir)
    log = root / f"{spec.case_id}.log"
    result = run_physics(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=(
            "Executioner/num_steps=1",
            "-snes_test_jacobian",
            "-snes_test_jacobian_view",
        ),
        timeout_seconds=timeout,
    )
    text = log.read_text(errors="replace")
    comparison = diagnose_jacobian_evidence(
        extract_jacobian_evidence(text),
        relative_tolerance=relative_tolerance,
    )
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "log": str(log),
        "comparison": comparison,
        "status": "PASS" if comparison.get("status") == "PASS" else "HOLD",
    }


def _verify_remedy_proxy(
    *,
    spec: CaseSpec,
    root: Path,
    exe: Path,
    timeout: float | None,
    ledger: ErrorLedger,
    run_id: str,
) -> dict[str, Any]:
    proxy_root = root / spec.case_id
    proxy_root.mkdir(parents=True)
    fields: dict[str, dict[str, Any]] = {}

    for field in ("E0", "Econst"):
        case_dir = proxy_root / field
        try:
            staged = stage_r3_proxy_case(spec, field, case_dir)
            fields[field] = {
                "case_dir": str(case_dir),
                "stage": staged,
                "status": "STAGED",
                "passed": False,
            }
        except Exception as exc:
            fields[field] = {
                "case_dir": str(case_dir),
                "status": "CONSTRUCTION_FAIL",
                "passed": False,
                "error": str(exc),
            }
            _record_event(
                ledger,
                run_id=run_id,
                stage="VERIFY_P1",
                case_id=f"{spec.case_id}:{field}",
                code="REMEDY_PROXY_CONSTRUCTION_FAIL",
                message=str(exc),
                source_layer="master_diagnostic_proxy_builder",
                signals=AttributionSignals(assistant_generated_contract_violation=True),
            )

    if not all(item["status"] == "STAGED" for item in fields.values()):
        return {
            "proxy_case": spec.case_id,
            "status": "HOLD_CONSTRUCTION",
            "passed": False,
            "secondary_owner_exposed": False,
            "fields": fields,
        }

    p2_pass = True
    for field, item in fields.items():
        case_dir = Path(item["case_dir"])
        p2 = _p2_case(
            exe=exe,
            case_dir=case_dir,
            log=proxy_root / f"{field}_p2.log",
            timeout=timeout,
        )
        item["p2"] = p2
        if p2["returncode"] == 0 and not p2["timed_out"]:
            item["status"] = "P2_PASS"
        else:
            item["status"] = "P2_FAIL"
            p2_pass = False
            _record_event(
                ledger,
                run_id=run_id,
                stage="VERIFY_P2",
                case_id=f"{spec.case_id}:{field}",
                code="REMEDY_PROXY_P2_FAIL",
                message="full-R3 remedy proxy failed --check-input",
                source_layer="framework_or_generated_input",
                signals=AttributionSignals(),
                evidence=p2,
            )

    if not p2_pass:
        return {
            "proxy_case": spec.case_id,
            "status": "HOLD_P2",
            "passed": False,
            "secondary_owner_exposed": False,
            "fields": fields,
        }

    for field, item in fields.items():
        case_dir = Path(item["case_dir"])
        p3 = _p3_case(
            exe=exe,
            case_dir=case_dir,
            log=proxy_root / f"{field}_p3.log",
            timeout=timeout,
        )
        item.update(p3)
        item["status"] = "PASS" if p3["passed"] else "FAIL"

    passed = all(item.get("passed") is True for item in fields.values())
    secondary = not passed
    if secondary:
        _record_event(
            ledger,
            run_id=run_id,
            stage="VERIFY_P3",
            case_id=spec.case_id,
            code="REMEDY_PROXY_R3_VERIFICATION_FAIL",
            message="atomic-owner remedy proxy did not recover both full R3-E0 and R3-Econst",
            source_layer="secondary_fault_detection",
            signals=AttributionSignals(contract_conformant=True),
            evidence={
                field: {
                    "returncode": item.get("returncode"),
                    "timed_out": item.get("timed_out"),
                    "failure_signature": item.get("failure_signature"),
                    "electron_residuals": item.get("electron_residuals"),
                }
                for field, item in fields.items()
            },
        )
    return {
        "proxy_case": spec.case_id,
        "status": "PASS" if passed else "SECONDARY_FAILURE_EXPOSED",
        "passed": passed,
        "secondary_owner_exposed": secondary,
        "fields": fields,
    }


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    results_root = args.results_root.resolve() if args.results_root else exe.parent / "temp" / "results"
    results_root.mkdir(parents=True, exist_ok=True)
    root = create_collision_safe_directory(results_root, f"r3_master_{utc_timestamp()}")
    run_id = root.name
    ledger = ErrorLedger.for_run(root, persistent_path=args.error_ledger)
    cases_root = root / "cases"
    logs_root = root / "logs"
    jac_root = root / "jacobian"
    verification_root = root / "verification"
    cases_root.mkdir(); logs_root.mkdir(); jac_root.mkdir(); verification_root.mkdir()

    identity = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "qpx_realpath": str(exe),
        "qpx_sha256": sha256_file(exe),
        "electron_reference_case": str(ELECTRON_REFERENCE_CASE),
        "frozen_diffusion": FROZEN_DIFFUSION,
        "frozen_mobility": FROZEN_MOBILITY,
        "geometry": "HELD_FIXED_OUT_OF_SCOPE",
        "case_ids": [spec.case_id for spec in CHEAP_CASES],
    }
    write_json_bundle(root, {"identity": ("identity.json", identity)})

    cases: dict[str, dict[str, Any]] = {}
    construction_failed = False
    for spec in CHEAP_CASES:
        target = cases_root / spec.case_id
        try:
            staged = stage_master_case(spec, target)
            cases[spec.case_id] = {
                "spec": {"family": spec.family, "kind": spec.kind, "meaning": spec.meaning, "transforms": list(spec.transforms)},
                "stage": staged,
                "status": "STAGED",
                "passed": False,
            }
        except Exception as exc:
            construction_failed = construction_failed or spec.kind == "required"
            cases[spec.case_id] = {
                "spec": {"family": spec.family, "kind": spec.kind, "meaning": spec.meaning, "transforms": list(spec.transforms)},
                "status": "CONSTRUCTION_FAIL",
                "passed": False,
                "error": str(exc),
            }
            _record_event(
                ledger, run_id=run_id, stage="P1", case_id=spec.case_id,
                code="GENERATED_CASE_CONTRACT_VIOLATION", message=str(exc),
                source_layer="master_diagnostic_case_builder",
                signals=AttributionSignals(assistant_generated_contract_violation=True),
            )

    if construction_failed:
        summary = {"status": "HOLD", "reason": "required case construction failed", "cases": cases}
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        ledger.write_summaries(root)
        print(f"R3_MASTER_ROOT: {root}")
        print("R3_MASTER_P1: FAIL")
        return 2

    required_p2_failure = False
    for spec in CHEAP_CASES:
        case = cases[spec.case_id]
        if case["status"] != "STAGED":
            continue
        p2 = _p2_case(
            exe=exe,
            case_dir=cases_root / spec.case_id,
            log=logs_root / f"{spec.case_id}_p2.log",
            timeout=args.timeout,
        )
        case["p2"] = p2
        if p2["returncode"] == 0 and not p2["timed_out"]:
            case["status"] = "P2_PASS"
            continue
        if spec.kind == "optional":
            case["status"] = "SKIPPED_UNSUPPORTED"
            _record_event(
                ledger, run_id=run_id, stage="P2", case_id=spec.case_id,
                code="OPTIONAL_CASE_UNSUPPORTED", message="optional diagnostic case failed --check-input",
                source_layer="framework_compatibility",
                signals=AttributionSignals(), evidence=p2,
            )
        else:
            case["status"] = "P2_FAIL"
            required_p2_failure = True
            _record_event(
                ledger, run_id=run_id, stage="P2", case_id=spec.case_id,
                code="REQUIRED_CASE_P2_FAIL", message="required diagnostic case failed --check-input",
                source_layer="framework_or_generated_input",
                signals=AttributionSignals(), evidence=p2,
            )

    if required_p2_failure:
        summary = {"status": "HOLD", "reason": "required P2 preflight failed; no P3 runtime launched", "cases": cases}
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        ledger.write_summaries(root)
        print(f"R3_MASTER_ROOT: {root}")
        print("R3_MASTER_P2: FAIL REQUIRED")
        return 2

    for spec in CHEAP_CASES:
        case = cases[spec.case_id]
        if case["status"] != "P2_PASS":
            continue
        p3 = _p3_case(
            exe=exe,
            case_dir=cases_root / spec.case_id,
            log=logs_root / f"{spec.case_id}_p3.log",
            timeout=args.timeout,
        )
        case.update(p3)
        case["status"] = "PASS" if p3["passed"] else "FAIL"
        if not p3["passed"]:
            _record_event(
                ledger, run_id=run_id, stage="P3", case_id=spec.case_id,
                code="RUNTIME_OR_CONVERGENCE_FAIL", message="diagnostic case did not satisfy runtime/checker contract",
                source_layer="qpx_runtime",
                signals=AttributionSignals(contract_conformant=True),
                evidence={k: p3[k] for k in ("returncode", "timed_out", "failure_signature", "electron_residuals", "coefficient_contract_pass")},
            )

    decision = classify_matrix(cases)

    jacobians: dict[str, Any] = {}
    for case_id in decision.get("selected_jacobian_cases", []):
        spec = CASE_BY_ID[case_id]
        try:
            result = _jacobian_case(
                spec=spec,
                root=jac_root,
                exe=exe,
                timeout=args.jacobian_timeout,
                relative_tolerance=args.jacobian_tolerance,
            )
        except Exception as exc:
            result = {"status": "HOLD", "error": str(exc)}
        jacobians[case_id] = result
        if case_id in cases:
            cases[case_id]["jacobian_status"] = result.get("status")
            cases[case_id]["jacobian"] = result

    decision = classify_matrix(cases)

    verification: dict[str, Any] = {}
    proxy_ids = list(dict.fromkeys(
        owner.get("remedy_proxy_case")
        for owner in decision.get("owners", [])
        if owner.get("remedy_proxy_case")
    ))
    for proxy_id in proxy_ids:
        spec = CASE_BY_ID.get(proxy_id)
        if spec is None:
            verification[proxy_id] = {
                "status": "HOLD_UNKNOWN_PROXY",
                "passed": False,
                "secondary_owner_exposed": False,
            }
            continue
        verification[proxy_id] = _verify_remedy_proxy(
            spec=spec,
            root=verification_root,
            exe=exe,
            timeout=args.timeout,
            ledger=ledger,
            run_id=run_id,
        )

    secondary_owner_exposed = any(
        item.get("secondary_owner_exposed") is True for item in verification.values()
    )
    for owner in decision.get("owners", []):
        proxy_id = owner.get("remedy_proxy_case")
        owner["remedy_proxy_verification"] = verification.get(proxy_id) if proxy_id else None
    decision["verification"] = verification
    decision["secondary_owner_exposed"] = secondary_owner_exposed

    for owner in decision.get("owners", []):
        remedy = owner.get("remedy") or {}
        _record_event(
            ledger, run_id=run_id, stage="DECISION", case_id=owner.get("remedy_proxy_case"),
            code=f"ATOMIC_OWNER_{owner['owner']}",
            message=owner.get("mechanism", owner["owner"]),
            source_layer="scientific_fault_isolation",
            signals=AttributionSignals(
                contract_conformant=True,
                reproducible_runtime_failure=True,
                isolated_code_owner=owner["owner"],
            ),
            evidence={
                "evidence": owner.get("evidence", []),
                "geometry": decision.get("geometry"),
                "proxy_verification_status": (owner.get("remedy_proxy_verification") or {}).get("status"),
            },
            remedy=remedy.get("remedy"),
        )

    artifact_paths = write_json_bundle(
        root,
        {
            "case_matrix": ("case_matrix.json", cases),
            "jacobian_matrix": ("jacobian_matrix.json", jacobians),
            "verification_matrix": ("verification_matrix.json", verification),
            "final_diagnosis": ("final_diagnosis.json", decision),
        },
    )
    error_paths = ledger.write_summaries(root)
    final = {
        "status": decision.get("status"),
        "run_id": run_id,
        "root": str(root),
        "owners": decision.get("owners", []),
        "unresolved_active_owner": decision.get("unresolved_active_owner", []),
        "secondary_owner_exposed": secondary_owner_exposed,
        "geometry": decision.get("geometry"),
        "artifacts": artifact_paths,
        "error_stats": error_paths,
    }
    write_json_bundle(root, {"summary": ("summary.json", final)})

    print(f"R3_MASTER_ROOT: {root}")
    print("R3_MASTER_P2: PASS ALL REQUIRED")
    print(f"R3_MASTER_DECISION: {decision.get('status')}")
    print("R3_MASTER_OWNERS: " + json.dumps([item["owner"] for item in decision.get("owners", [])]))
    print(f"R3_MASTER_SECONDARY_OWNER_EXPOSED: {str(secondary_owner_exposed).lower()}")
    print(f"R3_MASTER_SUMMARY: {root / 'summary.json'}")
    return 0 if decision.get("status") in {"ISOLATED", "RESIDUAL_MATRIX_PASS"} else 1


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
