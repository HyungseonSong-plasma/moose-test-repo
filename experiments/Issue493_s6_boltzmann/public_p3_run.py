#!/usr/bin/env python3
"""Issue #493 public-only native P3 with bounded preflight profiling.

This runner never reads protected original rates, never changes physics inputs,
never starts P4, and never publishes raw Exodus, CSV or native solver logs.
Diagnostic mode samples B for up to 15 minutes and NEVER claims P3 PASS.
Full mode requires explicit authorization, runs B then C and demands 461 frames.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

import p3_diagnostics as diag

import public_p2_check as p2
from run_issue493 import verify_native_csv
from physics_harness.execution.native_gates import require_p1_success


class P3Error(RuntimeError):
    def __init__(self, reason: str, stage: str = "P3"):
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


def native_command(candidate: Path, staged: Path, layers: list[str],
                   case: str, variant: str) -> list[str]:
    if case not in p2.CASES or variant not in p2.VARIANTS:
        raise P3Error("UNRECOGNIZED_CASE_OR_ARM", "P0")
    if not layers or len(layers) != (10 if variant == "B" else 11):
        raise P3Error("WRONG_INPUT_LAYER_COUNT", "P0")
    cmd = ("exec /app/physics_app/physics-opt -i " +
           " ".join(shlex.quote(layer) for layer in layers) +
           " Outputs/file_base=issue493_outputs/run/plasma")
    return [
        "docker", "run", "--rm", "--network", "none",
        "--name", f"issue493-p3-{case}-{variant.lower()}",
        "--entrypoint", "/bin/bash", "--user", "0:0",
        "--workdir", "/case",
        "--env", "OXYGEN_RESEARCH_400=1",
        "--env", "OXYGEN_RESEARCH_FULL24=0",
        "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
        "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
        "--mount", f"type=bind,src={candidate.resolve()},dst=/app,readonly",
        "--mount", f"type=bind,src={staged.resolve()},dst=/case",
        p2.PINNED_OCI, "-lc", "set -euo pipefail; source /environment; " + cmd,
    ]


def classify_nonzero(log: Path, rc: int, timed_out: bool) -> str:
    if timed_out:
        return "P3_TIMEOUT"
    if rc in (125, 126, 127):
        return "P3_DOCKER_LAUNCH"
    try:
        with log.open("rb") as stream:
            stream.seek(max(0, log.stat().st_size - 262144))
            tail = stream.read().decode("utf-8", errors="replace").lower()
    except OSError:
        tail = ""
    if (("interpolat" in tail or "rate_table" in tail or "lookup" in tail)
            and any(x in tail for x in
                    ("out of range", "outside", "extrapolat", "out of bounds"))):
        return "P3_RATE_LOOKUP_DOMAIN"
    if rc in (-9, 137):
        return "P3_PROCESS_KILLED_OR_OOM"
    return "P3_SOLVER_NONZERO"


def run_solve(candidate: Path, staged: Path, layers: list[str], *,
              case: str, variant: str, log: Path, timeout: int,
              p1_evidence: Path, mode: str = "full") -> dict:
    # A stale or tampered binary cannot run P3, even after a valid P2.
    identity = require_p1_success(
        p1_evidence, source_root=candidate,
        binary=candidate / "physics_app/physics-opt",
        source_sha=p2.PINNED_CANDIDATE, image_ref=p2.PINNED_OCI,
    )
    if log.exists():
        raise P3Error("P3_LOG_ALREADY_EXISTS")
    output_dir = staged / "issue493_outputs/run"
    output_dir.mkdir(parents=True, exist_ok=False)
    command = native_command(candidate, staged, layers, case, variant)
    evidence = diag.monitor_solver(
        command, cwd=staged, log=log, case=case, variant=variant,
        timeout_seconds=timeout, heartbeat_seconds=60,
    )
    status = {
        "P3": "NOT_RUN",
        "exit_code": evidence["returncode"],  # null, not a fake 127, on timeout
        "timed_out": evidence["timed_out"],
        "wall_seconds": evidence["wall_seconds"],
        "timeout_budget_seconds": evidence["timeout_budget_seconds"],
        "last_reported_step": evidence["last_reported_step"],
        "last_reported_time_seconds": evidence["last_reported_time_seconds"],
        "last_cpu_percent": evidence["last_cpu_percent"],
        "max_observed_memory_bytes": evidence["max_observed_memory_bytes"],
        "termination": evidence["termination"],
        "p1_binary_sha256": identity["binary_sha256"],
        "p3_log_sha256": p2.sha(log),
    }
    if evidence["timed_out"]:
        status.update(
            P3="HOLD",
            reason=("P3_DIAGNOSTIC_BUDGET_END" if mode == "diagnostic"
                    else "P3_TIMEOUT"),
        )
        return status
    if not evidence["launched"]:
        status.update(P3="HOLD", reason="P3_LAUNCH_ERROR")
        return status
    rc = evidence["returncode"]
    if rc != 0:
        reason = classify_nonzero(log, rc, False)
        status.update(
            P3="HOLD" if reason in (
                "P3_DOCKER_LAUNCH", "P3_RATE_LOOKUP_DOMAIN",
                "P3_PROCESS_KILLED_OR_OOM"
            ) else "FAIL",
            reason=reason,
        )
        return status
    exodus = output_dir / "plasma.e"
    csv_file = output_dir / "plasma.csv"
    if not exodus.is_file() or not csv_file.is_file() or exodus.stat().st_size == 0:
        status.update(P3="FAIL", reason="P3_OUTPUT_MISSING")
        return status
    try:
        verify_native_csv(csv_file)
    except Exception:
        status.update(P3="FAIL", reason="P3_CSV_SCHEMA_OR_TIMEGRID")
        return status
    status.update(
        P3="PASS", reason=None, frames=461, t_end_seconds=0.0001,
        native_exodus_sha256=p2.sha(exodus),
        native_exodus_bytes=exodus.stat().st_size,
        native_csv_sha256=p2.sha(csv_file),
        native_csv_bytes=csv_file.stat().st_size,
    )
    return status


def run_case(args: argparse.Namespace) -> dict:
    if args.case not in p2.CASES or args.timeout_seconds < 1:
        raise P3Error("INVALID_CASE_OR_TIMEOUT", "P0")
    if args.mode not in ("diagnostic", "full"):
        raise P3Error("INVALID_EXECUTION_MODE", "P0")
    if args.mode == "diagnostic" and args.timeout_seconds > 900:
        raise P3Error("DIAGNOSTIC_BUDGET_EXCEEDS_15_MINUTES", "P0")
    if args.mode == "full" and not args.authorize_full_p3:
        raise P3Error("FULL_P3_EXPLICIT_ACK_REQUIRED", "P0")
    result = {
        "schema": "issue493_public_p3_native_v2", "case": args.case,
        "mode": args.mode,
        "source_sha": p2.PINNED_SOURCE,
        "candidate_sha": p2.PINNED_CANDIDATE,
        "oci_image": p2.PINNED_OCI,
        "P0": "NOT_RUN", "P1": "NOT_RUN", "P2": "NOT_RUN",
        "P3": "NOT_RUN", "P4": "NOT_RUN", "science": "SCIENCE_HOLD",
        "variants": {"B": {"P2": "NOT_RUN", "P3": "NOT_RUN"},
                     "C": {"P2": "NOT_RUN", "P3": "NOT_RUN"}},
    }
    try:
        control, historical, candidate = (p.resolve() for p in
                                          (args.control, args.historical, args.candidate))
        if args.output.exists():
            raise P3Error("OUTPUT_ROOT_ALREADY_EXISTS", "P0")
        args.output.mkdir(parents=True, mode=0o700)
        p2.preflight(control)
        result["P0"] = "PASS"
        p2.check_head(historical, p2.PINNED_SOURCE)
        p2.check_head(candidate, p2.PINNED_CANDIDATE)
        if shutil.which("docker") is None:
            raise P3Error("DOCKER_UNAVAILABLE", "P1")
        identity = require_p1_success(
            args.p1_evidence, source_root=candidate,
            binary=candidate / "physics_app/physics-opt",
            source_sha=p2.PINNED_CANDIDATE, image_ref=p2.PINNED_OCI,
        )
        result["P1"] = "PASS"
        result["p1_evidence_sha256"] = p2.sha(args.p1_evidence)
        result["p1_binary_sha256"] = identity["binary_sha256"]
        result["mesh_sha256"] = p2.sha(
            historical / p2.CHEM /
            "baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
        )
        manifest = json.loads((control / p2.DECKS / "manifest.json").read_text())
        for variant in p2.VARIANTS:  # B first, no C in diagnostic mode
            if args.mode == "diagnostic" and variant == "C":
                break
            rec = result["variants"][variant]
            case_dir = args.output / f"{args.case}_{variant}"
            layers = p2.stage(control, historical, args.case, variant, case_dir, manifest)
            check = p2.check_native(
                candidate, case_dir, layers,
                args.output / f"P2_{args.case}_{variant}.log",
                1200, args.p1_evidence,
            )
            rec.update({
                "P2": check["P2"], "p2_log_sha256": check["log_sha256"],
                "p2_exit_code": check["exit_code"],
                "p2_classification": check["classification"],
            })
            if check["P2"] != "PASS":
                rec.update(P3="NOT_RUN", reason="P2_NOT_PASS")
                result["blocker"] = f"{variant}_P2_NOT_PASS"
                break
            solve = run_solve(
                candidate, case_dir, layers, case=args.case, variant=variant,
                log=args.output / f"P3_{args.case}_{variant}.log",
                timeout=args.timeout_seconds, p1_evidence=args.p1_evidence,
                mode=args.mode,
            )
            rec.update(solve)
            if solve["P3"] != "PASS":
                result["blocker"] = f"{variant}_{solve['reason']}"
                break
        result["p2_passed_arms"] = [
            arm for arm in p2.VARIANTS if result["variants"][arm]["P2"] == "PASS"
        ]
        result["p2_not_run_arms"] = [
            arm for arm in p2.VARIANTS if result["variants"][arm]["P2"] == "NOT_RUN"
        ]
        result["p3_passed_arms"] = [
            arm for arm in p2.VARIANTS if result["variants"][arm]["P3"] == "PASS"
        ]
        result["P2"] = ("PASS" if len(result["p2_passed_arms"]) == 2 else "HOLD")
        result["P3"] = (
            "PASS" if args.mode == "full" and len(result["p3_passed_arms"]) == 2
            else "HOLD"
        )
    except Exception as exc:
        # Avoid printing unreviewed logs or paths into public Actions output.
        result["blocker"] = exc.reason if isinstance(exc, P3Error) else "STAGING_OR_GATE_ERROR"
        result["error_type"] = type(exc).__name__
    finally:
        result["P4"] = "NOT_RUN"
        result["science"] = "SCIENCE_HOLD"
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "non_sensitive_p3_status.json").write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n"
        )
    return result


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--p1-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=p2.CASES, required=True)
    parser.add_argument("--mode", choices=("diagnostic", "full"), required=True)
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--authorize-full-p3", action="store_true",
                        help="Explicitly acknowledge a full, expensive 460-step B/C run")
    args = parser.parse_args()
    if args.mode == "diagnostic":
        if args.authorize_full_p3:
            parser.error("full P3 authorization is not valid in diagnostic mode")
        args.timeout_seconds = args.timeout_seconds or 600
        if not 1 <= args.timeout_seconds <= 900:
            parser.error("diagnostic budget must be 1–900 seconds")
    else:
        if not args.authorize_full_p3:
            parser.error("full mode requires --authorize-full-p3")
        args.timeout_seconds = args.timeout_seconds or 8100
        if not 1 <= args.timeout_seconds <= 8100:
            parser.error("full P3 per-arm budget must be 1–8100 seconds")
    result = run_case(args)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["P3"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
