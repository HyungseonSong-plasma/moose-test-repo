#!/usr/bin/env python3
"""Run the governed canonical Issue #91 R3-E0/R3-Econst acceptance queue."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from experiments.Issue93_r3_electron_isolation.run import _electron_residuals
from qpx_harness.adapters.moose.nonlinear_solver import failure_signature, runtime_core_facts
from qpx_harness.evidence import (
    create_collision_safe_directory,
    utc_timestamp,
    write_json_bundle,
)
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, run_qpx, validate_executable
from experiments.historical_recipe_support.issue91_r3 import build_r3_input

ROOT = Path(__file__).resolve().parents[2]
CASE_ROOT = ROOT / "experiments" / "Issue91_real_qvt_r3"
CASES = (
    ("R3_E0", "r3_e0", 0.0),
    ("R3_ECONST", "r3_econst", 0.01),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_head() -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def _stage(case_id: str, source_name: str, field_strength: float, target: Path) -> dict[str, Any]:
    source = CASE_ROOT / source_name
    base = (source / "heavy_base.i").read_text()
    input_text, meta = build_r3_input(base, field_strength=field_strength)
    staging = stage_case(
        source,
        target,
        input_text=input_text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    return {
        "case_id": case_id,
        "field_strength_V_per_m": field_strength,
        "source": str(source.resolve()),
        "staging": staging,
        "construction": meta,
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


def _runtime(exe: Path, case_dir: Path, log: Path, timeout: float) -> dict[str, Any]:
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
        "runtime_facts": runtime_core_facts(
            text,
            returncode=result.returncode,
            coupled_scaling_variables=("n_e",),
        ),
        "electron_residuals": _electron_residuals(text),
        "log": str(log),
    }


def _write_physical_csv(case_dir: Path) -> dict[str, Any]:
    source = case_dir / "input_out.csv"
    target = case_dir / "input_out.physical.csv"
    if not source.is_file():
        return {"pass": False, "error": "missing input_out.csv"}
    with source.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        if not fieldnames or "time" not in fieldnames:
            return {"pass": False, "error": "scalar CSV has no time column"}
        rows = list(reader)
    physical = []
    for row in rows:
        try:
            time = float(row["time"])
        except (TypeError, ValueError):
            return {"pass": False, "error": f"invalid time value: {row.get('time')!r}"}
        if time > 1.0e-15:
            physical.append(row)
    if not physical:
        return {"pass": False, "error": "no positive-time physical rows"}
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(physical)
    return {
        "pass": True,
        "source_rows": len(rows),
        "physical_rows": len(physical),
        "path": str(target.resolve()),
    }


def _checker(case_dir: Path) -> dict[str, Any]:
    temporal = _write_physical_csv(case_dir)
    if temporal.get("pass") is not True:
        return {"pass": False, "temporal_csv": temporal}
    checker = (case_dir / "check.py").resolve()
    physical = (case_dir / "input_out.physical.csv").resolve()
    expected = (case_dir / "expected.json").resolve()
    proc = subprocess.run(
        [sys.executable, str(checker), str(physical), str(expected)],
        cwd=case_dir.resolve(),
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "pass": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-12000:],
        "temporal_csv": temporal,
    }


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        args.results_root,
        f"issue91_r3_acceptance_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    staged: dict[str, Any] = {}
    for case_id, source_name, field_strength in CASES:
        staged[case_id] = _stage(
            case_id,
            source_name,
            field_strength,
            cases_root / case_id,
        )

    summary: dict[str, Any] = {
        "issue": 91,
        "experiment": "issue91-canonical-r3-acceptance",
        "repository_head": _repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": _sha256(exe),
        "representation": "solver n_e == n_hat; physical n_e == n_e_value*n_hat",
        "staged": staged,
        "p2": {},
        "cases": {},
        "status": "NOT_RUN",
    }

    # Preflight both declared cases before spending the scientific runtime budget.
    for case_id, _, _ in CASES:
        case_dir = cases_root / case_id
        p2 = _p2(exe, case_dir, logs / f"{case_id.lower()}_p2.log", args.timeout)
        summary["p2"][case_id] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"P2_FAIL_{case_id}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE91_R3_ACCEPTANCE_ROOT: {root}")
            print(f"ISSUE91_R3_ACCEPTANCE_STATUS: {summary['status']}")
            return 2

    for case_id, _, _ in CASES:
        case_dir = cases_root / case_id
        result = _runtime(
            exe,
            case_dir,
            logs / f"{case_id.lower()}_runtime.log",
            args.timeout,
        )
        result["checker"] = _checker(case_dir)
        result["passed"] = (
            result["returncode"] == 0
            and result["checker"].get("pass") is True
        )
        summary["cases"][case_id] = result
        if not result["passed"]:
            summary["status"] = f"{case_id}_FAIL"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE91_R3_ACCEPTANCE_ROOT: {root}")
            print(f"ISSUE91_R3_ACCEPTANCE_STATUS: {summary['status']}")
            return 1

    summary["status"] = "R3_ACCEPTED"
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE91_R3_ACCEPTANCE_ROOT: {root}")
    print(f"ISSUE91_R3_ACCEPTANCE_STATUS: {summary['status']}")
    print(f"ISSUE91_R3_ACCEPTANCE_SUMMARY: {root / 'summary.json'}")
    return 0


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
