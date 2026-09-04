"""Run the bounded R3 electron-density scaling counterfactual campaign."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from experiments.Issue93_r3_electron_isolation.operator_decomposition import _check_accepted_qvt_csv
from experiments.Issue93_r3_electron_isolation.run import _electron_residuals
from qpx_harness.reasoning.jacobian import diagnose_jacobian_evidence
from qpx_harness.evidence import (
    create_collision_safe_directory,
    extract_jacobian_evidence,
    failure_signature,
    runtime_core_facts,
    utc_timestamp,
    write_json_bundle,
)
from qpx_harness.execution.runtime import resolve_executable, run_qpx, validate_executable

from .cases import R3_E0_DIR, N_E_REF, stage_n0, stage_r3_case

EXPERIMENT_ID = "r3-electron-scaling-counterfactual"
JACOBIAN_FORCE_NL_ABS_TOL = "1.0e-30"


def _last_csv(case_dir: Path) -> Path | None:
    direct = case_dir / "input_out.csv"
    if direct.is_file():
        return direct
    matches = sorted(case_dir.glob("input_out*.csv"))
    return matches[-1] if matches else None


def _run_case(exe: Path, case_dir: Path, log: Path, timeout: float) -> dict[str, Any]:
    result = run_qpx(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=("-snes_monitor", "-snes_converged_reason", "-ksp_converged_reason"),
        timeout_seconds=timeout,
    )
    text = log.read_text(errors="replace")
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "failure_signature": failure_signature(text),
        "runtime_facts": runtime_core_facts(text, returncode=result.returncode, coupled_scaling_variables=("n_e",)),
        "electron_residuals": _electron_residuals(text),
        "log": str(log),
    }


def _check_n0(case_dir: Path) -> dict[str, Any]:
    csv_path = _last_csv(case_dir)
    if csv_path is None:
        return {"pass": False, "error": "missing scalar CSV"}
    return _check_accepted_qvt_csv(csv_path, case_dir / "expected.json")


def _check_r3(case_dir: Path) -> dict[str, Any]:
    csv_path = _last_csv(case_dir)
    if csv_path is None:
        return {"pass": False, "error": "missing scalar CSV"}
    # The campaign may be launched with a relative --results-root. Once cwd is
    # changed to the staged case, passing that relative path again points at a
    # nonexistent nested results/... path. Resolve all checker inputs first.
    case_dir = case_dir.resolve()
    csv_path = csv_path.resolve()
    checker = (R3_E0_DIR / "check.py").resolve()
    expected = (case_dir / "expected.json").resolve()
    proc = subprocess.run(
        [sys.executable, str(checker), str(csv_path), str(expected)],
        cwd=case_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "pass": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-12000:],
    }


def _jacobian_extra_args() -> tuple[str, ...]:
    # N0 normally terminates at iteration zero because the normalized constant
    # residual is already ~1e-16 and nl_abs_tol=1e-14. Tighten only this
    # diagnostic invocation so PETSc actually forms/tests the Jacobian. The
    # runtime acceptance path keeps the physically appropriate absolute floor.
    return (
        "Executioner/num_steps=1",
        "Executioner/abort_on_solve_fail=true",
        f"Executioner/nl_abs_tol={JACOBIAN_FORCE_NL_ABS_TOL}",
        "-snes_test_jacobian",
    )


def _run_jacobian(exe: Path, case_dir: Path, log: Path, timeout: float) -> dict[str, Any]:
    result = run_qpx(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=_jacobian_extra_args(),
        timeout_seconds=timeout,
    )
    text = log.read_text(errors="replace")
    evidence = extract_jacobian_evidence(text)
    diagnosis = diagnose_jacobian_evidence(evidence, relative_tolerance=1.0e-6)
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "evidence": evidence,
        "diagnosis": diagnosis,
        "log": str(log),
    }


def _p2(exe: Path, case_dir: Path, log: Path, timeout: float) -> dict[str, Any]:
    result = run_qpx(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=("--check-input",),
        timeout_seconds=timeout,
    )
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "log": str(log),
    }


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(args.results_root, f"r3_electron_scaling_{stamp}")
    logs = root / "logs"
    cases_root = root / "cases"
    logs.mkdir(parents=True, exist_ok=True)
    cases_root.mkdir(parents=True, exist_ok=True)

    staged = {
        "N0": stage_n0(cases_root / "N0"),
        "N1_R3_E0": stage_r3_case(cases_root / "N1_R3_E0", field_strength=0.0),
        "N2_R3_ECONST": stage_r3_case(cases_root / "N2_R3_ECONST", field_strength=0.01),
    }
    summary: dict[str, Any] = {
        "experiment": EXPERIMENT_ID,
        "reference_density_m3": N_E_REF,
        "representation": "solver n_e == n_hat; physical n_e == 1e16*n_hat",
        "staged": staged,
        "p2": {},
        "cases": {},
        "jacobian": None,
        "status": "NOT_RUN",
    }

    # Preflight the entire declared matrix before any scientific runtime.
    for case_id in ("N0", "N1_R3_E0", "N2_R3_ECONST"):
        result = _p2(exe, cases_root / case_id, logs / f"{case_id.lower()}_p2.log", args.timeout)
        summary["p2"][case_id] = result
        if result["returncode"] != 0:
            summary["status"] = f"P2_FAIL_{case_id}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"R3_SCALING_ROOT: {root}")
            print(f"R3_SCALING_STATUS: {summary['status']}")
            return 2

    n0_dir = cases_root / "N0"
    n0 = _run_case(exe, n0_dir, logs / "n0_runtime.log", args.timeout)
    n0["checker"] = _check_n0(n0_dir)
    n0["passed"] = n0["returncode"] == 0 and n0["checker"].get("pass") is True
    summary["cases"]["N0"] = n0
    if not n0["passed"]:
        summary["status"] = "SCALING_REJECTED_N0"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"R3_SCALING_ROOT: {root}")
        print(f"R3_SCALING_STATUS: {summary['status']}")
        return 1

    summary["jacobian"] = _run_jacobian(
        exe,
        n0_dir,
        logs / "n0_jacobian.log",
        args.timeout,
    )
    jacobian_pass = summary["jacobian"]["diagnosis"].get("status") == "PASS"

    n1_dir = cases_root / "N1_R3_E0"
    n1 = _run_case(exe, n1_dir, logs / "n1_r3_e0_runtime.log", args.timeout)
    n1["checker"] = _check_r3(n1_dir)
    n1["passed"] = n1["returncode"] == 0 and n1["checker"].get("pass") is True
    summary["cases"]["N1_R3_E0"] = n1
    if not n1["passed"]:
        summary["status"] = "SCALING_CONFIRMED_R3_E0_FAIL"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"R3_SCALING_ROOT: {root}")
        print(f"R3_SCALING_STATUS: {summary['status']}")
        return 1

    n2_dir = cases_root / "N2_R3_ECONST"
    n2 = _run_case(exe, n2_dir, logs / "n2_r3_econst_runtime.log", args.timeout)
    n2["checker"] = _check_r3(n2_dir)
    n2["passed"] = n2["returncode"] == 0 and n2["checker"].get("pass") is True
    summary["cases"]["N2_R3_ECONST"] = n2
    if not n2["passed"]:
        summary["status"] = "SCALING_CONFIRMED_R3_ECONST_FAIL"
    elif not jacobian_pass:
        summary["status"] = "SCALING_R3_PASS_JACOBIAN_HOLD"
    else:
        summary["status"] = "SCALING_CONFIRMED_FULL_R3_PASS"
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"R3_SCALING_ROOT: {root}")
    print(f"R3_SCALING_STATUS: {summary['status']}")
    print(f"R3_SCALING_SUMMARY: {root / 'summary.json'}")
    return 0 if summary["status"] == "SCALING_CONFIRMED_FULL_R3_PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qpx", required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
