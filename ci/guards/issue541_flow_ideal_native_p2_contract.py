#!/usr/bin/env python3
"""Fail-closed FLOW package replacement for Issue402 EI/H legacy Native P2.

The historical workflow is retained until the exact-head live Native job,
external caller disposition, and historical artifact gates are all proved.
P2 input checks are syntax-only; never imply P3 or physical parity.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github/workflows/ci.yml"
OLD = ROOT / ".github/workflows/issue402-rate-coef-ideal-gas-native-once.yml"
OLD_BLOB = "64164c097ec8f7831e67b80b317144cd97ba9ee8"
JOB = "issue402_flow_ideal_native_p2"
OCI = (
    "ghcr.io/hyungseonsong-plasma/physics-build-base@"
    "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
)
REQUIRED = (
    "test \"$(git rev-parse HEAD)\" = \"$EXPECTED_HEAD\"",
    "github.event.pull_request.head.sha",
    "ci/guards/issue541_flow_ideal_native_p2_contract.py --self-test",
    "ci/guards/issue541_flow_ideal_native_p2_contract.py --check",
    "app_non_unity_dirs=\"%/utils\"",
    "python3 -m physics_app.ci.check_issue402_json_rate_native_p2",
    "--executable /workspace/physics_app/physics-opt",
    "--p1-identity /workspace/evidence/flow_ideal_native_p1_identity.json",
    "physics_app/ci/plasma_direct_existing_materials_smoke.i",
    "ISSUE402_FLOW_IDEAL_DIRECT_P2_PASS",
    "P3=NOT_RUN",
    "SCIENCE_HOLD",
    "actions/upload-artifact@v4",
    "retention-days: 30",
)


def blob_sha(text: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(text)).encode() + b"\0" + text).hexdigest()


def job_text(ci: str) -> str:
    marker = "  " + JOB + ":"
    if ci.count(marker) != 1:
        return ""
    return marker + ci.split(marker, 1)[1].split(
        "\n  plasma_native_regression:", 1
    )[0]


def validate(ci: str, old: bytes | None) -> list[str]:
    failures: list[str] = []
    job = job_text(ci)
    if not job:
        failures.append("new Native P2 job missing or duplicated")
    for token in (*REQUIRED, OCI):
        if token not in job:
            failures.append("native replacement missing contract: " + token)
    for bypass in ("|| true", "continue-on-error:", "P3=PASS", "workflow_dispatch:"):
        if bypass in job:
            failures.append("native replacement bypass/unsafe trigger: " + bypass)
    if old is None:
        failures.append("legacy workflow removed before caller and evidence gates")
    elif blob_sha(old) != OLD_BLOB:
        failures.append("pinned original legacy workflow blob changed")
    return failures


def self_test(ci: str, old: bytes) -> None:
    assert not validate(ci, old), validate(ci, old)
    for token in REQUIRED:
        corrupted = ci.replace(token, "REMOVED_OWNERSHIP_TOKEN")
        assert validate(corrupted, old), token
    for bypass in ("|| true", "continue-on-error:", "P3=PASS"):
        marker = "  " + JOB + ":"
        assert validate(ci.replace(marker, marker + "\n    # " + bypass, 1), old)
    assert validate(ci, None)
    assert validate(ci, old + b"\n# unexpected change\n")
    print("ISSUE402_FLOW_IDEAL_NATIVE_P2_MUTATION_SELF_TEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.self_test and not args.check:
        parser.error("select --self-test or --check")
    ci = CI.read_text(encoding="utf-8")
    old = OLD.read_bytes() if OLD.is_file() else None
    if args.self_test:
        if old is None:
            raise SystemExit("old workflow missing before retirement gate")
        self_test(ci, old)
    if args.check:
        failures = validate(ci, old)
        if failures:
            raise SystemExit("\n".join(failures))
        print("ISSUE402_FLOW_IDEAL_NATIVE_P2_CONTRACT=PASS; P3=NOT_RUN; SCIENCE_HOLD")


if __name__ == "__main__":
    main()
