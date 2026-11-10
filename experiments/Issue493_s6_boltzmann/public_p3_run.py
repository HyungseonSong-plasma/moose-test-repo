#!/usr/bin/env python3
"""Issue #493 public-only native P3: S6-417/941, B then C, 460 steps each.

This runner never reads protected original rates, never changes physics inputs,
never starts P4, and never publishes raw Exodus, CSV or native solver logs.
One GitHub Actions matrix lane owns one case; matrix max-parallel is two.
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
              p1_evidence: Path) -> dict:
    # P1 identity is checked again immediately before EACH full P3 solve.
    identity = require_p1_success(
        p1_evidence, source_root=candidate,
        binary=candidate / "physics_app/physics-opt",
        source_sha=p2.PINNED_CANDIDATE, image_ref=p2.PINNED_OCI,
    )
    if log.exists():
        raise P3Error("P3_LOG_ALREADY_EXISTS")
    output_dir = staged / "issue493_outputs/run"
    output_dir.mkdir(parents=True, exist_ok=False)
    cmd = native_command(candidate, staged, layers, case, variant)
    name = f"issue493-p3-{case}-{variant.lower()}"
    start = time.monotonic()
    timed_out = False
    rc = 127
    with log.open("x", encoding="utf-8") as handle:
        try:
            run = subprocess.run(
                cmd, cwd=staged, stdout=handle, stderr=subprocess.STDOUT,
                timeout=timeout, check=False,
            )
            rc = run.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            # Killing docker CLI alone can leave its container running.
            try:
                subprocess.run(["docker", "rm", "-f", name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=45, check=False)
            except (OSError, subprocess.SubprocessError):
                pass
        except OSError:
            rc = 127
    status = {
        "P3": "NOT_RUN", "exit_code": rc, "timed_out": timed_out,
        "wall_seconds": round(time.monotonic() - start, 3),
        "p1_binary_sha256": identity["binary_sha256"],
        "p3_log_sha256": p2.sha(log),
    }
    if timed_out or rc != 0:
        reason = classify_nonzero(log, rc, timed_out)
        status.update(P3="HOLD" if reason in
                      ("P3_TIMEOUT", "P3_DOCKER_LAUNCH", "P3_RATE_LOOKUP_DOMAIN",
                       "P3_PROCESS_KILLED_OR_OOM") else "FAIL",
                      reason=reason)
        return status
    exodus = output_dir / "plasma.e"
    csv_file = output_dir / "plasma.csv"
    if not exodus.is_file() or not csv_file.is_file() or exodus.stat().st_size == 0:
        status.update(P3="FAIL", reason="P3_OUTPUT_MISSING")
        return status
    try:
        verify_native_csv(csv_file)  # exactly 461 finite rows, 0..100us
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
    result = {
        "schema": "issue493_public_p3_native_v1", "case": args.case,
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
        for variant in p2.VARIANTS:  # B then C: never start C after B failure
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
            )
            rec.update(solve)
            if solve["P3"] != "PASS":
                result["blocker"] = f"{variant}_{solve['reason']}"
                break
        result["P2"] = ("PASS" if all(
            result["variants"][arm]["P2"] == "PASS" for arm in p2.VARIANTS
        ) else "HOLD")
        result["P3"] = ("PASS" if all(
            result["variants"][arm]["P3"] == "PASS" for arm in p2.VARIANTS
        ) else "HOLD")
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
    parser.add_argument("--timeout-seconds", type=int, default=8100)
    args = parser.parse_args()
    result = run_case(args)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["P3"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
