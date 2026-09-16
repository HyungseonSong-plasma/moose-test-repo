#!/usr/bin/env python3
"""Write the per-case Wave-O manifest after the v4 runtime wrapper finishes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from experiments.Issue236_m1a_multiapp_smoke import run_om_forensic_ci as om

_REQUIRED_TRACE_KEYS = (
    "accepted_parent_times",
    "accepted_child",
    "parent_attempts",
    "parent_nonlinear",
    "petsc_monitor",
    "terminal_om_error",
)


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--recorder", choices=("off", "on"), required=True)
    parser.add_argument("--wrapper-rc", type=int, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--logs-root", type=Path, required=True)
    parser.add_argument("--physics-opt", type=Path, required=True)
    args = parser.parse_args()

    args.logs_root.mkdir(parents=True, exist_ok=True)
    summary_path = args.results_root / "summary.json"
    runtime_log = args.results_root / "runtime.log"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        summary = {}

    runtime = summary.get("runtime") if isinstance(summary.get("runtime"), dict) else {}
    analysis = summary.get("analysis") if isinstance(summary.get("analysis"), dict) else {}
    forensic = analysis.get("om_forensic") if isinstance(analysis.get("om_forensic"), dict) else {}
    trajectory = forensic.get("trajectory") if isinstance(forensic.get("trajectory"), dict) else {}
    hashes = trajectory.get("hashes") if isinstance(trajectory.get("hashes"), dict) else {}
    payloads = trajectory.get("payloads") if isinstance(trajectory.get("payloads"), dict) else {}
    contract = trajectory.get("execution_contract") if isinstance(trajectory.get("execution_contract"), dict) else {}

    input_paths = sorted(path for path in args.results_root.rglob("*.i") if path.is_file())
    input_hashes = {
        str(path.relative_to(args.results_root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in input_paths
    }
    observer_hashes = {
        str(path.relative_to(args.results_root)): om.canonical_observer_input_hash(
            path.read_text(encoding="utf-8")
        )
        for path in input_paths
    }

    log_text = runtime_log.read_text(encoding="utf-8", errors="replace") if runtime_log.is_file() else ""
    solver_rc = runtime.get("returncode")
    timed_out = runtime.get("timed_out")
    physics_started = isinstance(solver_rc, int) and runtime_log.is_file() and runtime_log.stat().st_size > 0
    expected_om_error = (
        "Species 'Om' has Y=" in log_text and forensic.get("om_error_signature_present") is True
    )
    trajectory_complete = all(
        isinstance(payloads.get(key), list)
        and len(payloads[key]) > 0
        and isinstance(hashes.get(key), str)
        and len(hashes[key]) == 64
        for key in _REQUIRED_TRACE_KEYS
    )
    serial_observed = (
        contract.get("serial_observed") is True
        and isinstance(contract.get("observed_num_processors"), list)
        and len(contract["observed_num_processors"]) > 0
        and all(value == 1 for value in contract["observed_num_processors"])
        and isinstance(contract.get("observed_num_threads"), list)
        and len(contract["observed_num_threads"]) > 0
        and all(value == 1 for value in contract["observed_num_threads"])
    )
    runtime_valid = (
        physics_started
        and solver_rc != 0
        and timed_out is False
        and args.wrapper_rc == 1
        and expected_om_error
        and bool(input_hashes)
        and trajectory_complete
        and serial_observed
    )

    manifest = {
        "schema": "ISSUE236_OM_WAVE_O_ARTIFACT_V3",
        "state": "FINAL_VALIDATED" if runtime_valid else "FINAL_INVALID",
        "case": args.case,
        "recorder": args.recorder,
        "git_sha": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "build_base": os.environ.get("BUILD_BASE_REF"),
        "dependencies": {
            "MOOSE": os.environ.get("MOOSE_SHA"),
            "CRANE": os.environ.get("CRANE_SHA"),
            "SQUIRREL": os.environ.get("SQUIRREL_SHA"),
            "ZAPDOS": os.environ.get("ZAPDOS_SHA"),
        },
        "physics_opt_sha256": _sha(args.physics_opt),
        "physics_opt_started": physics_started,
        "solver_returncode": solver_rc,
        "wrapper_returncode": args.wrapper_rc,
        "timed_out": timed_out,
        "expected_om_error": expected_om_error,
        "trajectory_complete": trajectory_complete,
        "serial_runtime_observed": serial_observed,
        "runtime_evidence_valid": runtime_valid,
        "runtime_log_sha256": _sha(runtime_log),
        "input_sha256": input_hashes,
        "observer_input_sha256": observer_hashes,
        "trajectory_hashes": hashes,
        "summary_sha256": _sha(summary_path),
    }
    (args.logs_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
