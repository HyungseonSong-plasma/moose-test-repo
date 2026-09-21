#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GENERATED = ROOT / "generated"
RESULTS = ROOT / "results"
BUILD_BASE_REF = (
    "ghcr.io/hyungseonsong-plasma/physics-build-base@"
    "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
)
CASES = ("ref_chi0p1", "onepass_chi5", "gummel_chi5")


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _docker(script: str) -> None:
    _run(["docker", "pull", BUILD_BASE_REF])
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            "--user",
            "0:0",
            "--workdir",
            "/workspace",
            "-v",
            f"{REPO}:/workspace",
            BUILD_BASE_REF,
            "-lc",
            script,
        ]
    )


def _prepare() -> None:
    _run([sys.executable, str(ROOT / "prepare.py")])


def p1() -> None:
    _prepare()
    case_args = " ".join(
        f"python3 /workspace/bin/physics.py preflight /workspace/experiments/Issue253_g1_gummel_dt_release/generated/{name}/input.i"
        for name in CASES
    )
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; "
        + "; ".join(
            f"python3 /workspace/bin/physics.py preflight /workspace/experiments/Issue253_g1_gummel_dt_release/generated/{name}/input.i"
            for name in CASES
        )
    )
    _docker(script)
    print("ISSUE253_G1_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        _prepare()
    checks = "; ".join(
        (
            "cd /workspace/experiments/Issue253_g1_gummel_dt_release/generated/"
            f"{name} && /workspace/physics_app/physics-opt --check-input -i input.i "
            f"> /workspace/experiments/Issue253_g1_gummel_dt_release/results/{name}_p2.log 2>&1"
        )
        for name in CASES
    )
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        "mkdir -p /workspace/experiments/Issue253_g1_gummel_dt_release/results; "
        "make -C /workspace/physics_app -j2; "
        "test -x /workspace/physics_app/physics-opt; "
        + checks
    )
    _docker(script)
    print("ISSUE253_G1_P2: PASS")


def p3() -> None:
    exe = REPO / "physics_app" / "physics-opt"
    if not exe.exists():
        raise SystemExit("physics-opt missing: P2 must complete before P3")
    runs = "; ".join(
        (
            "cd /workspace/experiments/Issue253_g1_gummel_dt_release/generated/"
            f"{name} && /workspace/physics_app/physics-opt -i input.i "
            "-snes_monitor -snes_converged_reason -ksp_converged_reason "
            f"> /workspace/experiments/Issue253_g1_gummel_dt_release/results/{name}_runtime.log 2>&1"
        )
        for name in CASES
    )
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        + runs
    )
    _docker(script)
    _run([sys.executable, str(ROOT / "analyze.py")])
    print("ISSUE253_G1_P3: EVIDENCE_READY")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("p1", "p2", "p3"))
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.phase == "p1":
        p1()
    elif args.phase == "p2":
        p2()
    else:
        p3()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
