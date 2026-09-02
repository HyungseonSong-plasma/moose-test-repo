#!/usr/bin/env python3
"""Run Issue #93 J0 + J1; P3 is one governed scientific EVR."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from experiments.Issue93_r3_electron_isolation.check import CheckError, check_csv
from experiments.Issue93_r3_electron_isolation.dependency_audit import AuditError, audit
from experiments.Issue93_r3_electron_isolation.prepare import (
    DEFAULT_DT,
    PrepareError,
    SOURCE_CASE,
    prepare_case,
)

DEFAULT_TIMEOUT = 300
N_E_RESIDUAL_RE = re.compile(r"\bn_e\s*[:=]\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


class RunError(RuntimeError):
    pass


def _resolve_qpx(value: str) -> str:
    p = Path(value).expanduser()
    if "/" in value:
        if not p.is_file():
            raise RunError(f"qpx executable does not exist: {p}")
        return str(p.resolve())
    found = shutil.which(value)
    if not found:
        raise RunError(f"qpx executable not found on PATH: {value}")
    return found


def _run(cmd: list[str], cwd: Path, log: Path, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output = result.stdout or ""
        rc = result.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        rc = 124
        raw = exc.stdout or ""
        output = raw.decode() if isinstance(raw, bytes) else raw
        output += f"\nISSUE93_TIMEOUT_AFTER_SECONDS={timeout}\n"
    elapsed = time.monotonic() - started
    log.write_text(output)
    return {
        "cmd": cmd,
        "returncode": rc,
        "timed_out": timed_out,
        "wall_s": elapsed,
        "log": str(log),
    }


def _electron_residuals(text: str) -> list[float]:
    return [float(m.group(1)) for m in N_E_RESIDUAL_RE.finditer(text)]


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def run(args: argparse.Namespace) -> int:
    source = args.source_case.resolve()
    # J0 is qpx-free and completed before resolving/launching QPX.
    j0 = audit(source)
    qpx = _resolve_qpx(args.qpx)

    root = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix="issue93_j1_"))
    case = root / "case"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    _write_json(root / "j0_dependency_audit.json", j0)
    prepare = prepare_case(case, source, args.dt)

    summary: dict[str, Any] = {
        "issue": 93,
        "stage": "J1_FROZEN_HEAVY_ELECTRON_DISCRIMINATOR",
        "artifact_root": str(root),
        "source_case": str(source),
        "qpx": qpx,
        "j0": j0,
        "prepare": prepare,
        "p2": None,
        "p3": None,
        "checker": None,
        "electron_residuals": [],
        "scientific_evr_consumed": 0,
        "scientific_acceptance_eligible": False,
        "decision": "NOT_RUN",
    }

    p2 = _run([qpx, "-i", "input.i", "--check-input"], case, logs / "p2_check_input.log", args.timeout)
    summary["p2"] = p2
    if p2["returncode"] != 0:
        summary["decision"] = "J1_CONSTRUCTION_OR_FRAMEWORK_CONTRACT_FAIL"
        _write_json(root / "summary.json", summary)
        print("ISSUE93_J1_P2: FAIL")
        print("ISSUE93_J1_DECISION: J1_CONSTRUCTION_OR_FRAMEWORK_CONTRACT_FAIL")
        print("ISSUE93_EVR: 0")
        print(f"ARTIFACT_ROOT: {root}")
        return 2

    # Exactly one J1 P3 launch. Any returned scientific runtime result consumes EVR1.
    p3 = _run(
        [
            qpx,
            "-i",
            "input.i",
            "-snes_monitor",
            "-snes_converged_reason",
            "-ksp_converged_reason",
        ],
        case,
        logs / "j1_runtime.log",
        args.timeout,
    )
    summary["p3"] = p3
    summary["scientific_evr_consumed"] = 1
    runtime_text = Path(p3["log"]).read_text()
    summary["electron_residuals"] = _electron_residuals(runtime_text)

    checker = None
    csv_path = case / "input_out.csv"
    if csv_path.is_file():
        try:
            checker = check_csv(csv_path)
        except (CheckError, OSError, ValueError) as exc:
            checker = {"pass": False, "error": str(exc)}
    else:
        checker = {"pass": False, "error": "input_out.csv not produced"}
    summary["checker"] = checker

    if p3["returncode"] == 0 and checker.get("pass") is True:
        decision = "J1_LINEAR_ELECTRON_PATH_SUPPORTED"
        rc = 0
    else:
        decision = "J1_ELECTRON_PATH_BLOCKER_REPRODUCED_OR_RUNTIME_FAILED"
        rc = 1
    summary["decision"] = decision
    _write_json(root / "summary.json", summary)

    print("ISSUE93_J1_P2: PASS")
    print(f"ISSUE93_J1_P3_RC: {p3['returncode']}")
    print(f"ISSUE93_J1_DECISION: {decision}")
    print(f"ISSUE93_J1_ELECTRON_RESIDUALS: {summary['electron_residuals']}")
    print("ISSUE93_EVR: 1")
    print("SCIENTIFIC_ACCEPTANCE_ELIGIBLE: false")
    print(f"ARTIFACT_ROOT: {root}")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qpx", required=True)
    parser.add_argument("--source-case", type=Path, default=SOURCE_CASE)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--dt", type=float, default=DEFAULT_DT)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()
    if args.dt <= 0 or args.timeout <= 0:
        parser.error("--dt and --timeout must be positive")
    try:
        return run(args)
    except (RunError, AuditError, PrepareError, OSError, ValueError, KeyError) as exc:
        print(f"ISSUE93_J1_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
