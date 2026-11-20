#!/usr/bin/env python3
"""FLOW-only P0 replacement contract for historical Issue402 EI/H ideal-gas once.

This guard checks the independent canonical CI *invocation surface* only.
It cannot establish Native P1/P2/P3 acceptance or zero external consumers.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github/workflows/physics-code-ci.yml"
JOB = "issue402_ideal_gas_p0"

PYTEST_TARGETS = (
    "tests/test_issue402_json_rate_unification.py",
    "tests/test_issue402_rate_coef_ideal_gas.py",
    "tests/test_electron_impact_rate_material_prefix.py",
    "tests/test_issue402_no_legacy_material_registration.py",
    "tests/test_issue402_reaction_reduction_p2_only.py",
    "tests/test_issue402_retired_plasma_closures.py",
    "tests/characterization/test_issue395_ei17_overlay.py",
    "tests/characterization/test_issue192_s5r.py",
    "tests/characterization/test_issue192_s5r_runtime.py",
)
STAGE5_CHECKS = (
    "check_stage5_s5d_heavy_reactions.py --static",
    "check_stage5_s5d_heavy_reactions.py --self-test",
    "check_stage5_h05_runtime.py --static",
    "check_stage5_s5r_assembly.py --static",
    "check_stage5_s5r_assembly.py --self-test",
)
SOURCE_ASSERTIONS = (
    "test ! -e physics_app/include/utils/PhysicsReactionDatabase.h",
    "test ! -e physics_app/src/utils/PhysicsReactionDatabase.C",
    "test ! -e physics_app/src/materials/RateCoeffMaterial.C",
    "test ! -e physics_app/src/materials/HeavyReactionRateMaterial.C",
    "test -e physics_app/src/materials/EIRateCoefMaterial.C",
    "test -e physics_app/src/materials/HRateCoefMaterial.C",
    "test ! -e physics_app/data/heavy_reactions/stage5_s5d_oxygen_heavy.txt",
    "test ! -e physics_app/data/heavy_reactions/stage5_s5e_h05_oxygen_heavy.txt",
)


def extract_job(workflow: str) -> str:
    marker = "  " + JOB + ":"
    if workflow.count(marker) != 1:
        return ""
    tail = workflow.split(marker, 1)[1].splitlines(keepends=True)
    # Stop at the next top-level YAML job, not at a shared section comment.
    # Adjacent independent jobs may reuse identical pytest paths.
    for i, line in enumerate(tail):
        if line.startswith("  ") and not line.startswith("   ") and line.strip().endswith(":") and not line.lstrip().startswith("#"):
            return marker + "".join(tail[:i])
    return marker + "".join(tail)


def validate(job: str) -> list[str]:
    failures: list[str] = []
    needed = (
        "test \"$(git rev-parse HEAD)\" = \"$EXPECTED_HEAD\"",
        "github.event.pull_request.head.sha || github.sha",
        "issue402_ideal_gas_p0_contract.py --self-test",
        "issue402_ideal_gas_p0_contract.py --check",
        "set -euo pipefail",
        "JSON_HEAVY_SURFACE_P0_PASS",
        "P3=NOT_RUN",
        "SCIENCE_HOLD",
        *PYTEST_TARGETS,
        *STAGE5_CHECKS,
        *SOURCE_ASSERTIONS,
        "PhysicsReactionRateMaterial",
        "PhysicsSurfaceReactionMaterial",
    )
    if not job:
        failures.append("canonical FLOW ideal-gas P0 job missing or duplicated")
    for token in needed:
        if token not in job:
            failures.append("missing historical P0 owner: " + token)
    for forbidden in ("|| true", "continue-on-error:", "--check-input", "docker run", "physics-opt --", "P3=PASS"):
        if forbidden in job:
            failures.append("P0 job contains prohibited bypass or Native claim: " + forbidden)
    return failures


def self_test() -> None:
    job = extract_job(CI.read_text(encoding="utf-8"))
    assert not validate(job), validate(job)
    for token in (*PYTEST_TARGETS, *STAGE5_CHECKS, *SOURCE_ASSERTIONS):
        broken = job.replace(token, "REMOVED_HISTORICAL_P0_OWNER", 1)
        assert validate(broken), token
    for token in ("test \"$(git rev-parse HEAD)\" = \"$EXPECTED_HEAD\"", "P3=NOT_RUN"):
        assert validate(job.replace(token, "")), token
    for forbidden in ("|| true", "docker run", "continue-on-error:"):
        assert validate(job + "\n" + forbidden), forbidden
    print("ISSUE402_IDEAL_GAS_P0_MUTATION_SELF_TEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.self_test and not args.check:
        parser.error("select --self-test and/or --check")
    if args.self_test:
        self_test()
    if args.check:
        failures = validate(extract_job(CI.read_text(encoding="utf-8")))
        if failures:
            raise SystemExit("\n".join(failures))
        print("ISSUE402_IDEAL_GAS_P0_CONTRACT_PASS; P3=NOT_RUN; SCIENCE_HOLD")


if __name__ == "__main__":
    main()
