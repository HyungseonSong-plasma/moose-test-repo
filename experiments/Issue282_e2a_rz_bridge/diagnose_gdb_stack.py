#!/usr/bin/env python3
"""Issue282: bounded *native* RZ SIGSEGV stack-trace capture.

Research diagnostics only; no physics/model changes or scientific signoff.
Use the exact immutable published PhysicsApp image as base and install a
debugger in an EPHEMERAL derivative. Run the same generated historical inputs
under GDB, so missing symbols, changed behavior, or debugger unavailability
are reported as INCONCLUSIVE rather than as a physical verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.Issue282_e2a_rz_bridge.diagnose_segv import make_case
from experiments.Issue282_e2a_rz_bridge.run_native import IMAGE

HERE = Path(__file__).resolve().parent
CASES = ("r4_qf1_predecessor", "e2a_zero_diffusion")
# Immutable hashes from prior actual RZ automatic_scaling=false artifact #13515972554.
INPUT_SHA256 = {
    "r4_qf1_predecessor": "3a1c472f90590fece531eb6c2dca3bb1b47340a99464851ef5331d6cac67ea5b",
    "e2a_zero_diffusion": "7a6151b07eb02bf61215f1e24ac7cdf3cd9c1e792d6f08cf3d2529e2b9a609f9",
}
MESH_SHA256 = "a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e"
DEBUG_IMAGE = "physics282-rz-gdb:local"
DEFAULT_OUTPUT = HERE / "gdb_stack_results"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def call(argv: list[str], log: Path, *, timeout: int = 240, input_text: str | None = None) -> int:
    """Preserve stdout/stderr even if launching the debugging tool fails."""
    try:
        cp = subprocess.run(argv, input=input_text, capture_output=True, text=True, timeout=timeout)
        log.write_text(
            "argv=" + repr(argv) + "\nreturncode=" + str(cp.returncode) +
            "\nstdout:\n" + cp.stdout + "\nstderr:\n" + cp.stderr,
            encoding="utf-8",
        )
        return cp.returncode
    except Exception:
        log.write_text(traceback.format_exc(), encoding="utf-8")
        return -1


def debug_dockerfile() -> str:
    # Runtime is a minimal image without even a named root passwd entry.
    # Install debugger only in an isolated Ubuntu stage, then COPY its whole
    # rootfs below /opt/physics282_debugroot. No RUN, apt, shell, libc upgrade,
    # or package install occurs in the original PhysicsApp filesystem.
    return f"""FROM ubuntu:24.04 AS debugger
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gdb && rm -rf /var/lib/apt/lists/*
FROM {IMAGE}
COPY --from=debugger / /opt/physics282_debugroot/
USER 0
"""


DEBUG_ROOT = "/opt/physics282_debugroot"
DEBUG_LOADER = DEBUG_ROOT + "/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
DEBUG_LIBRARY_PATH = (
    DEBUG_ROOT + "/lib/x86_64-linux-gnu:" +
    DEBUG_ROOT + "/usr/lib/x86_64-linux-gnu"
)
DEBUG_GDB = DEBUG_ROOT + "/usr/bin/gdb"


def debug_gdb_command(*arguments: str) -> list[str]:
    # Explicit dynamic loader/library path prevents an Ubuntu GDB install from
    # replacing the *actual* PhysicsApp runtime libc/MOOSE shared libraries.
    return [
        "--entrypoint", DEBUG_LOADER, DEBUG_IMAGE,
        "--library-path", DEBUG_LIBRARY_PATH, DEBUG_GDB, *arguments,
    ]


def docker_entrypoint(image_config: dict) -> list[str]:
    entrypoint = image_config.get("Config", {}).get("Entrypoint")
    if not isinstance(entrypoint, list) or not entrypoint or any(
        not isinstance(part, str) or not part for part in entrypoint
    ):
        raise ValueError("immutable PhysicsApp image has no explicit binary entrypoint")
    if entrypoint[0] in ("sh", "/bin/sh", "bash", "/bin/bash"):
        raise ValueError("shell entrypoint must be resolved to the actual binary first")
    return entrypoint


def prepare(results: Path, report: dict) -> None:
    for case_name in CASES:
        case_dir = results / case_name
        row = {"status": "STAGING", "expected_input_sha256": INPUT_SHA256[case_name]}
        report["cases"][case_name] = row
        try:
            stage = make_case(case_dir, case_name)
            row.update(stage)
            actual = sha256(case_dir / "input.i")
            actual_mesh = sha256(case_dir / "qvt.msh")
            row["input_sha256"] = actual
            row["mesh_sha256"] = actual_mesh
            row["status"] = (
                "INPUT_MATCH_PREVIOUS_RUN"
                if actual == INPUT_SHA256[case_name] and actual_mesh == MESH_SHA256
                else "INPUT_DRIFT_NO_DEBUG"
            )
        except Exception as exc:
            row["status"] = "STAGING_FAILED"
            row["error"] = repr(exc)
            row["traceback"] = traceback.format_exc()
        finally:
            write_json(results / "manifest.json", report)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()
    results = args.results.resolve()
    if not results.is_relative_to(ROOT):
        raise ValueError("results must be under the Physics checkout for artifact upload")
    results.mkdir(parents=True, exist_ok=True)
    report = {
        "issue": 282,
        "evidence_class": "RZ_NATIVE_BACKTRACE_ONLY",
        "science_acceptance": "PENDING_INDEPENDENT_PHYSICS_VALIDATOR",
        "image_pinned": IMAGE,
        "debug_image_ephemeral": DEBUG_IMAGE,
        "reference_artifact_id": 13515972554,
        "source_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
        ).strip(),
        "cases": {},
    }
    write_json(results / "manifest.json", report)
    prepare(results, report)
    if any(r["status"] != "INPUT_MATCH_PREVIOUS_RUN" for r in report["cases"].values()):
        report["verdict"] = "INCONCLUSIVE_INPUT_DRIFT_OR_STAGING"
        write_json(results / "manifest.json", report)
        return 1
    if args.prepare_only:
        report["verdict"] = "PREPARED_MATCHING_INPUTS_ONLY"
        write_json(results / "manifest.json", report)
        return 0

    # Original image binary/entrypoint provenance, before debugger installation.
    try:
        image = subprocess.check_output(["docker", "image", "inspect", IMAGE], text=True)
        (results / "original-image-inspect.json").write_text(image, encoding="utf-8")
        config = json.loads(image)[0]
        entrypoint = docker_entrypoint(config)
        report["original_entrypoint"] = entrypoint
        report["original_repo_digests"] = config.get("RepoDigests")
    except Exception as exc:
        report["verdict"] = "INCONCLUSIVE_IMAGE_ENTRYPOINT"
        report["error"] = repr(exc)
        write_json(results / "manifest.json", report)
        return 1
    write_json(results / "manifest.json", report)

    dockerfile = debug_dockerfile()
    (results / "debug.Dockerfile").write_text(dockerfile, encoding="utf-8")
    build_rc = call(
        ["docker", "build", "--pull=false", "-t", DEBUG_IMAGE, "-"],
        results / "debug-image-build.log", input_text=dockerfile, timeout=600,
    )
    report["debug_image_build_rc"] = build_rc
    if build_rc:
        report["verdict"] = "INCONCLUSIVE_DEBUGGER_INSTALL"
        write_json(results / "manifest.json", report)
        return 1

    call(
        ["docker", "image", "inspect", DEBUG_IMAGE],
        results / "debug-image-inspect.log",
    )
    preflight_rc = call(
        ["docker", "run", "--rm", "--network", "none",
         *debug_gdb_command("--version")],
        results / "debugger-environment.log",
    )
    report["debugger_preflight_rc"] = preflight_rc
    if preflight_rc:
        report["verdict"] = "INCONCLUSIVE_DEBUGGER_PRECHECK"
        write_json(results / "manifest.json", report)
        return 1
    success = True
    for case_name in CASES:
        case = results / case_name
        relative = case.relative_to(ROOT).as_posix()
        row = report["cases"][case_name]
        base = ["docker", "run", "--rm", "--network", "none",
                "-v", f"{ROOT}:/workspace", "-w", f"/workspace/{relative}"]
        p2_rc = call(
            [*base, IMAGE, "--check-input", "-i", "input.i"],
            case / "original-image-check.log", timeout=180,
        )
        row["original_P2_rc"] = p2_rc
        if p2_rc:
            row["status"] = "ORIGINAL_P2_FAILED"
            success = False
            write_json(results / "manifest.json", report)
            continue

        # All MOOSE physics, mesh, step and other solver settings unchanged.
        # GDB stops (does not pass through) the first SIGSEGV and prints all stacks.
        command = [
            "docker", "run", "--rm", "--network", "none",
            "--cap-add=SYS_PTRACE", "--security-opt", "seccomp=unconfined",
            "-v", f"{ROOT}:/workspace", "-w", f"/workspace/{relative}",
            *debug_gdb_command("--batch", "--quiet"),
            "-ex", "set pagination off",
            "-ex", "set confirm off",
            # Minimal PhysicsApp image has no /bin/sh; GDB must exec binary directly.
            "-ex", "set startup-with-shell off",
            "-ex", "set print frame-arguments all",
            "-ex", "handle SIGSEGV stop print nopass",
            "-ex", "run",
            "-ex", "info program",
            "-ex", "thread apply all bt 40",
            "-ex", "info sharedlibrary",
            "-ex", "info registers",
            "--args", *entrypoint, "-i", "input.i",
        ]
        rc = call(command, case / "gdb-stack.log", timeout=240)
        log = (case / "gdb-stack.log").read_text(encoding="utf-8")
        row["gdb_returncode"] = rc
        row["segv_captured"] = "Program received signal SIGSEGV" in log
        row["stack_frames_present"] = "#0 " in log
        row["status"] = (
            "FIRST_SIGSEGV_STACK_CAPTURED_UNSYMBOLIZED_OR_SYMBOLIZED"
            if row["segv_captured"] and row["stack_frames_present"]
            else "INCONCLUSIVE_DEBUGGER_OR_BEHAVIOR_CHANGED"
        )
        success &= row["segv_captured"] and row["stack_frames_present"]
        write_json(results / "manifest.json", report)
    report["verdict"] = (
        "BOTH_NATIVE_CRASH_STACKS_CAPTURED_NOT_SCIENCE_ACCEPTED"
        if success else "INCONCLUSIVE_DEBUG_STACK_INCOMPLETE"
    )
    write_json(results / "manifest.json", report)
    print(json.dumps({"status": report["verdict"],
                      "cases": {k: v["status"] for k, v in report["cases"].items()}},
                     sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
