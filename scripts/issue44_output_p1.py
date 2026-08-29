#!/usr/bin/env python3
"""Issue #44 user-local P1 framework-effective output-contract preflight.

This runner is intentionally P1-only. It builds the existing v5 feedback-small
input, evaluates the explicit micro-time output contract, and invokes the real
user-local qpx-opt with --check-input/--show-input/--show-outputs. It never
enters a physics P3 run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import fast_plasma_relaxation_v2 as v2
from qpx_harness import fast_plasma_relaxation_v5 as v5
from qpx_harness import output_observation_contract as ooc
from qpx_harness.preflight import validate_parser_symbols_text
from qpx_harness.runtime import resolve_executable, run_command, validate_executable


class Issue44P1Error(RuntimeError):
    pass


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _create_root(results_root: Path) -> Path:
    results_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"issue44_output_p1_{stamp}"
    root = results_root / stem
    index = 1
    while root.exists():
        root = results_root / f"{stem}_{index:02d}"
        index += 1
    root.mkdir()
    return root


def _build_probe(repo_root: Path, case_dir: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    base_case = repo_root / v2.v1.BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise Issue44P1Error(f"missing accepted qvt electron control: {base_case}")

    mesh = v2.mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()
    input_text = v5._build_feedback_v5(
        base_text,
        dt=v2.DT_FEEDBACK_SMALL,
        steps=v2.N_STEPS,
        radial_span=radial_span,
    )
    validate_parser_symbols_text(input_text)

    report = ooc.observation_report(
        input_text,
        required_time_separation=v2.DT_FEEDBACK_SMALL,
    )
    decision = ooc.evaluate_observation_report(report)
    if decision.get("status") != "PASS":
        raise Issue44P1Error(
            "generated v5 input failed the explicit output-observation contract"
        )

    shutil.copytree(base_case, case_dir)
    v2.v1._purge_runtime_artifacts(case_dir)
    input_path = case_dir / "issue44_p1.i"
    input_path.write_text(input_text)
    return input_path, report, decision


def run_p1(*, qpx: str | None, results_root: str | None) -> int:
    exe = resolve_executable(qpx)
    validate_executable(exe)

    root = _create_root(
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    case_dir = root / "case"
    log_path = root / "p1_qpx_show_input_outputs.log"
    summary_path = root / "summary.json"

    input_path, static_report, static_decision = _build_probe(ROOT, case_dir)

    command = [
        str(exe),
        "-i",
        input_path.name,
        "--check-input",
        "--show-input",
        "--show-outputs",
        "--no-color",
    ]
    run = run_command(
        command,
        cwd=case_dir,
        log_path=log_path,
        stream=False,
    )

    log_size = log_path.stat().st_size if log_path.is_file() else 0
    qpx_check = "PASS" if run.returncode == 0 else "FAIL"
    evidence = "RECORDED" if run.returncode == 0 and log_size > 0 else "MISSING"
    status = (
        "PASS"
        if static_decision.get("status") == "PASS"
        and run.returncode == 0
        and log_size > 0
        else "HOLD"
    )

    summary = {
        "issue": 44,
        "phase": "P1",
        "status": status,
        "claim": (
            "real user-local qpx-opt accepts the explicit v5 micro-time output "
            "configuration and records parsed-input/output-scheduling evidence "
            "without entering physics P3"
        ),
        "executable": {
            "realpath": str(exe),
            "sha256": _sha256(exe),
        },
        "input": {
            "path": str(input_path),
            "dt": v2.DT_FEEDBACK_SMALL,
            "steps": v2.N_STEPS,
        },
        "static_output_contract": {
            "report": static_report,
            "decision": static_decision,
        },
        "qpx_preflight": {
            "command": command,
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "check_input": qpx_check,
            "show_input_requested": True,
            "show_outputs_requested": True,
            "log": str(log_path),
            "log_size_bytes": log_size,
            "framework_effective_evidence": evidence,
        },
        "p3_executed": False,
    }
    _write_json(summary_path, summary)

    print(f"ISSUE44_P1_STATIC_CONTRACT: {static_decision.get('status')}")
    print(f"ISSUE44_P1_QPX_CHECK_INPUT: {qpx_check}")
    print(f"ISSUE44_P1_FRAMEWORK_EVIDENCE: {evidence}")
    print(f"ISSUE44_P1_PRECLASS: {status}")
    print(f"ISSUE44_P1_LOG: {log_path}")
    print(f"ISSUE44_P1_SUMMARY: {summary_path}")
    return 0 if status == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Issue #44 P1-only qpx-opt output-contract preflight; "
            "does not execute physics P3"
        )
    )
    parser.add_argument("--qpx", help="path to canonical user-local qpx-opt")
    parser.add_argument("--results-root", help="optional evidence root")
    args = parser.parse_args(argv)
    return run_p1(qpx=args.qpx, results_root=args.results_root)


if __name__ == "__main__":
    raise SystemExit(main())
