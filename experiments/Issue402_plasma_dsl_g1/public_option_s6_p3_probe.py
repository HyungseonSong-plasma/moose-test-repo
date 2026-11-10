#!/usr/bin/env python3
"""Bounded P3 *startup probe* for merged Issue402 S6-417/941 B-vs-D.

Never call the probe a 460-step comparison. Never publish native logs, CSV,
Exodus, source rate-table bytes or sensitive paths. This reuses the actual
P2-exact-head success and the same Native P1 binary within one CI job.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

import public_option_s6_p2 as opt

CASES = ("417", "941")
VARIANTS = ("B", "D")
PROGRESS = re.compile(r"(?im)^\s*(?:Time Step\s+|Step\s+)(\d+)")
TIME = re.compile(r"(?im)^\s*Time\s*[:=]\s*([0-9.eE+-]+)")
OCI = opt.OCI


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def require_p2_gate(evidence: Path, source_sha: str, binary: Path) -> dict:
    path = evidence / "issue402_option_s6_p2_status.json"
    if not path.is_file():
        raise ValueError("MISSING_EXACT_HEAD_PUBLIC_P2_GATE")
    gate = json.loads(path.read_text())
    if (gate.get("P0") != "PASS" or gate.get("P2") != "PASS" or
        gate.get("cleanup") != "PASS" or gate.get("status") != "PASS" or
        gate.get("science") != "SCIENCE_HOLD" or
        gate.get("identity", {}).get("source_sha") != source_sha or
        gate.get("identity", {}).get("build_image") != OCI or
        gate.get("identity", {}).get("binary_sha256") != digest(binary) or
        gate.get("option_overlay_sha256") != opt.OVERLAY_SHA256):
        raise ValueError("PUBLIC_P2_GATE_IDENTITY_OR_VERDICT_MISMATCH")
    if any(gate.get("checks", {}).get(c, {}).get(v, {}).get("P2") != "PASS"
           for c in CASES for v in VARIANTS):
        raise ValueError("FOUR_WAY_PUBLIC_P2_NOT_PASS")
    opt.validate_overlay()
    return {"status": "PASS", "binary_sha256": digest(binary), "source_sha": source_sha}


def run_probe(source: Path, binary: Path, case_dir: Path, layers: list[str],
              case: str, variant: str, timeout_seconds: int, log: Path) -> dict:
    if timeout_seconds <= 0 or len(layers) != (10 if variant == "B" else 11):
        raise ValueError("INVALID_P3_PROBE_INPUT")
    name = f"issue402-p3-probe-{case}-{variant.lower()}"
    output = case_dir / "issue402_probe"
    output.mkdir(exist_ok=False)
    case_home = case_dir / ".probe_home"
    case_home.mkdir(exist_ok=False)
    # The full, pinned 460-step input is unchanged. A wall-clock watchdog
    # bounds diagnostic execution, rather than shortening its physics grid.
    native = ("exec /workspace/physics_app/physics-opt -i " +
              " ".join(shlex.quote(x) for x in layers) +
              " Outputs/file_base=issue402_probe/plasma")
    argv = [
        "docker", "run", "--rm", "--network", "none",
        "--name", name, "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--entrypoint", "/bin/bash",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--workdir", "/case",
        "--env", "HOME=/case/.probe_home",
        "--env", "XDG_CACHE_HOME=/case/.probe_home",
        "--env", "OXYGEN_RESEARCH_400=1",
        "--env", "OXYGEN_RESEARCH_FULL24=0",
        "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
        "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
        "--mount", f"type=bind,src={source.resolve()},dst=/workspace,readonly",
        "--mount", f"type=bind,src={case_dir.resolve()},dst=/case",
        OCI, "-lc", "set -euo pipefail; source /environment; " + native,
    ]
    started = time.monotonic()
    rc = 127
    timed_out = False
    with log.open("x", encoding="utf-8") as stream:
        try:
            rc = subprocess.run(argv, cwd=case_dir, stdout=stream,
                                stderr=subprocess.STDOUT,
                                timeout=timeout_seconds, check=False).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                subprocess.run(["docker", "rm", "-f", name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=40, check=False)
            except (OSError, subprocess.SubprocessError):
                pass
    if not log.is_file():
        raise ValueError("NO_NATIVE_PROBE_LOG")
    text = log.read_text(errors="replace")
    steps = [int(x) for x in PROGRESS.findall(text)]
    times = []
    for t in TIME.findall(text):
        try:
            value = float(t)
            if 0 <= value <= 0.0001:
                times.append(value)
        except ValueError:
            pass
    startup = ("Framework Information" in text and
               "Executioner:" in text and
               "Input File(s):" in text)
    classification = (
        "PROBE_TIME_CAP_REACHED" if timed_out else
        "FULL_RUN_RETURNED_ZERO" if rc == 0 else
        "NATIVE_PROBE_LAUNCH_OR_LINK_FAILURE" if rc in (125, 126, 127) else
        "NATIVE_PROBE_SOLVER_NONZERO"
    )
    # Probe never awards a full P3 PASS based on a truncated execution.
    return {
        "classification": classification,
        "native_startup_verified": startup,
        "timed_out": timed_out,
        "return_code": rc if not timed_out else None,
        "wall_seconds": round(time.monotonic() - started, 2),
        "largest_printed_step": max(steps) if steps else None,
        "largest_printed_time_seconds": max(times) if times else None,
        "log_sha256": digest(log),
        "P3_460_step_parity": "NOT_PROVEN",
        "science": "SCIENCE_HOLD",
    }


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=90)
    args = parser.parse_args()
    report = {
        "schema": "issue402.public_s6_p3_bounded_probe.v1",
        "science": "SCIENCE_HOLD", "P3_460_step_parity": "NOT_PROVEN",
        "P4": "NOT_RUN", "status": "HOLD", "cases": {},
    }
    outcome = 3
    try:
        if args.seconds < 30 or args.seconds > 300:
            raise ValueError("INVALID_BOUNDED_PROBE_DURATION")
        source = opt.ROOT
        historical = args.historical.resolve()
        binary = args.binary.resolve()
        evidence = args.evidence.resolve()
        gate = require_p2_gate(evidence, args.source_sha, binary)
        opt.check_source(args.source_sha, historical, binary)
        report.update(source_sha=args.source_sha, binary_sha256=gate["binary_sha256"],
                      watchdog_seconds=args.seconds)
        manifest = json.loads((source / opt.p2.DECKS / "manifest.json").read_text())
        with tempfile.TemporaryDirectory(prefix="issue402_p3_probe_",
                                         dir=os.getenv("RUNNER_TEMP", None)) as scratch:
            for case in CASES:
                report["cases"][case] = {}
                for variant in VARIANTS:
                    if digest(binary) != gate["binary_sha256"]:
                        raise ValueError("P1_BINARY_MUTATED_DURING_PROBE")
                    workspace = Path(scratch) / f"{case}_{variant}"
                    layers = opt.p2.stage(source, historical, case,
                                          "B" if variant == "B" else "C",
                                          workspace, manifest)
                    if variant == "D":
                        overlay = workspace / opt.p2.CHEM / "migrated_continuity.i"
                        overlay.write_text(opt.OVERLAY, encoding="utf-8")
                        if digest(overlay) != opt.OVERLAY_SHA256:
                            raise ValueError("OPTION_D_OVERLAY_SHA_MISMATCH")
                    log = workspace / "p3_probe.log"
                    status = run_probe(source, binary, workspace, layers, case,
                                       variant, args.seconds, log)
                    report["cases"][case][variant] = status
                    report["status"] = "IN_PROGRESS_PROBE_ONLY"
                    target = evidence / "issue402_p3_bounded_probe_status.json"
                    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        items = [report["cases"][c][v] for c in CASES for v in VARIANTS]
        report["status"] = (
            "P3_PROBE_STARTUP_VERIFIED__FULL_PARITY_NOT_PROVEN"
            if all(p["native_startup_verified"] for p in items)
            else "P3_PROBE_STARTUP_NOT_PROVEN"
        )
        outcome = 0 if all(p["native_startup_verified"] for p in items) else 3
    except Exception as exc:
        report["status"] = "P3_PROBE_HOLD"
        report["blocker_class"] = type(exc).__name__
        report["blocker"] = str(exc)[:160] if isinstance(exc, ValueError) else "PROBE_INFRASTRUCTURE_ERROR"
    finally:
        args.evidence.mkdir(parents=True, exist_ok=True)
        (args.evidence / "issue402_p3_bounded_probe_status.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        # Do not output per-case native log content or raw physical values.
        print(json.dumps({"status": report["status"],
                          "science": "SCIENCE_HOLD",
                          "P3_460_step_parity": "NOT_PROVEN",
                          "cases": {k: {v: {"classification": x.get("classification"),
                                             "startup": x.get("native_startup_verified"),
                                             "step": x.get("largest_printed_step")}
                                         for v, x in item.items()}
                                    for k, item in report["cases"].items()}},
                         sort_keys=True))
    return outcome


if __name__ == "__main__":
    sys.exit(main())
