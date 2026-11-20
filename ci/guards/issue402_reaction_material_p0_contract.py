#!/usr/bin/env python3
"""Fail-closed exact-target replacement contract for retired Issue402 P0-only workflow.

A static check cannot replace the independent, real P0 execution in canonical CI.
The retired Git blob is preserved in repository history.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github/workflows/physics-legacy-audit.yml"
LEGACY = ROOT / ".github/workflows/issue402-reaction-material-reduction-p0-once.yml"
JOB = "issue402_reaction_material_p0"

PYTEST_TARGETS = (
    "tests/characterization/test_issue192_s5r.py",
    "tests/characterization/test_issue192_s5r_runtime.py",
    "tests/test_issue402_s6_chemistry_run_templates.py",
    "tests/test_issue402_chemistry_mechanism_contract.py"
)
CHECK_COMMANDS = (
    "physics_app/ci/check_r2_o2_ionization_implementation.py",
    "physics_app/ci/check_r3_o2s_excitation_implementation.py",
    "physics_app/ci/check_e8_ei10_energy_contract.py",
    "physics_app/ci/check_e8_ei10_energy_implementation.py",
    "physics_app/ci/check_e8_ei10_energy_runtime.py --self-test",
    "physics_app/ci/check_e8_ei16_energy_contract.py",
    "physics_app/ci/check_e8_ei16_energy_runtime.py --self-test",
    "physics_app/ci/check_standard_moose_energy_projection.py --self-test",
    "physics_app/ci/check_stage5_s5r_assembly.py --self-test",
    "physics_app/ci/check_stage5_s5r_ei16_recovery.py"
)


def extract_job(workflow: str) -> str:
    marker = "  " + JOB + ":"
    parts = workflow.split(marker)
    if len(parts) != 2:
        return ""
    tail = parts[1].splitlines(keepends=True)
    # Test this job only; following independent jobs may have overlapping targets.
    for i, line in enumerate(tail):
        if line.startswith("  ") and not line.startswith("   ") and line.strip().endswith(":") and not line.lstrip().startswith("#"):
            return marker + "".join(tail[:i])
    return marker + "".join(tail)


def validate(job: str, legacy: str | None) -> list[str]:
    failures: list[str] = []
    needed = [
        "test \"$(git rev-parse HEAD)\" = \"$EXPECTED_HEAD\"",
        "github.event.pull_request.head.sha || github.sha",
        "issue402_reaction_material_p0_contract.py --self-test",
        "issue402_reaction_material_p0_contract.py --check",
        *PYTEST_TARGETS,
        *CHECK_COMMANDS,
    ]
    for token in needed:
        if token not in job:
            failures.append("missing canonical P0 owner: " + token)
    if "|| true" in job:
        failures.append("canonical P0 job must not suppress failures")
    if legacy is not None:
        for token in (*PYTEST_TARGETS, *CHECK_COMMANDS):
            if token not in legacy:
                failures.append("legacy source unexpectedly differs: " + token)
    return failures


def self_test() -> None:
    job = extract_job(CI.read_text(encoding="utf-8"))
    legacy = LEGACY.read_text(encoding="utf-8") if LEGACY.exists() else None
    assert job, "canonical job missing"
    assert not validate(job, legacy), validate(job, legacy)
    for token in (*PYTEST_TARGETS, *CHECK_COMMANDS):
        corrupted = job.replace(token, "REMOVED_P0_OWNERSHIP", 1)
        assert any(token in e for e in validate(corrupted, legacy)), token
    assert validate(job.replace('test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"', ""), legacy)
    print("ISSUE402_REACTION_MATERIAL_P0_MUTATION_SELF_TEST=PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.check:
        job = extract_job(CI.read_text(encoding="utf-8"))
        legacy = LEGACY.read_text(encoding="utf-8") if LEGACY.exists() else None
        failures = validate(job, legacy)
        for failure in failures:
            print(failure)
        if failures:
            print("ISSUE402_REACTION_MATERIAL_P0_OWNER=FAIL")
            return 1
        print("ISSUE402_REACTION_MATERIAL_P0_OWNER=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
