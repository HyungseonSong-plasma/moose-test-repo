#!/usr/bin/env python3
"""Fail-closed proof of a 20,400s B-only P3 completion attempt.

Aggregate P3 remains HOLD even when B reaches 461 frames; C/P4 are NOT_RUN.
This prints only sanitized metrics and never includes raw simulation outputs.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys

EXPECTED_SOURCE = "29d1acc6ef7969908b86719e4b95c73a1565136d"
EXPECTED_CANDIDATE = "bebaf47a33ff5ee1d6b933d9691bf48f5ec0f947"
EXPECTED_OCI = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
BUDGET_SECONDS = 20400


def validate(report: dict, case: str) -> dict:
    if case not in {"417", "941"} or report.get("case") != case:
        raise ValueError("B_COMPLETION_CASE_MISMATCH")
    if report.get("schema") != "issue493_public_p3_native_v2" or report.get("mode") != "complete-b":
        raise ValueError("B_COMPLETION_SCHEMA_OR_MODE")
    if (report.get("source_sha") != EXPECTED_SOURCE
            or report.get("candidate_sha") != EXPECTED_CANDIDATE
            or report.get("oci_image") != EXPECTED_OCI):
        raise ValueError("B_COMPLETION_PIN_MISMATCH")
    if report.get("P0") != "PASS" or report.get("P1") != "PASS":
        raise ValueError("B_COMPLETION_NATIVE_GATES_MISSING")
    if (report.get("P2") != "HOLD" or report.get("P3") != "HOLD"
            or report.get("P4") != "NOT_RUN"
            or report.get("science") != "SCIENCE_HOLD"):
        raise ValueError("B_COMPLETION_AGGREGATE_FALSE_PASS")
    arms = report.get("variants", {})
    b, c = arms.get("B", {}), arms.get("C", {})
    if (b.get("P2") != "PASS" or c.get("P2") != "NOT_RUN"
            or c.get("P3") != "NOT_RUN"
            or report.get("p2_passed_arms") != ["B"]
            or report.get("p2_not_run_arms") != ["C"]):
        raise ValueError("B_COMPLETION_C_FORBIDDEN")
    if b.get("timeout_budget_seconds") != BUDGET_SECONDS:
        raise ValueError("B_COMPLETION_WRONG_BUDGET")
    wall = b.get("wall_seconds")
    if type(wall) not in (float, int) or not math.isfinite(wall) or not 0 <= wall <= BUDGET_SECONDS + 120:
        raise ValueError("B_COMPLETION_INVALID_WALL_TIME")
    for key in ("last_reported_step", "heartbeat_samples", "native_log_bytes"):
        value = b.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("B_COMPLETION_BAD_TELEMETRY")
    if b.get("P3") == "PASS":
        if (b.get("exit_code") != 0 or b.get("timed_out") is not False
                or b.get("termination") != "EXIT"
                or b.get("frames") != 461
                or b.get("t_end_seconds") != 0.0001
                or report.get("p3_passed_arms") != ["B"]):
            raise ValueError("B_COMPLETION_FALSE_SOLVE_PASS")
        for key in ("native_exodus_sha256", "native_csv_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(b.get(key, ""))):
                raise ValueError("B_COMPLETION_OUTPUT_HASH_ABSENT")
        for key in ("native_exodus_bytes", "native_csv_bytes"):
            if type(b.get(key)) is not int or b[key] <= 0:
                raise ValueError("B_COMPLETION_EMPTY_OUTPUT")
    elif b.get("P3") == "HOLD":
        if (b.get("reason") != "P3_TIMEOUT"
                or b.get("timed_out") is not True
                or b.get("exit_code") is not None
                or b.get("termination") != "TIMEOUT"
                or report.get("p3_passed_arms") != []):
            raise ValueError("B_COMPLETION_UNCLASSIFIED_HOLD")
    else:
        raise ValueError("B_COMPLETION_SOLVER_FAILURE")
    return {
        "event": "PUBLIC_P3_B_COMPLETION_VERDICT",
        "case": case,
        "b_p2": "PASS", "b_p3": b["P3"],
        "b_reason": b.get("reason"),
        "b_frames": b.get("frames"),
        "b_wall_seconds": wall,
        "b_last_reported_step": b.get("last_reported_step"),
        "b_t_end_seconds": b.get("t_end_seconds"),
        "b_max_cpu_percent": b.get("max_observed_cpu_percent"),
        "b_max_memory_bytes": b.get("max_observed_memory_bytes"),
        "c_p3": "NOT_RUN", "aggregate_p3": "HOLD",
        "p4": "NOT_RUN", "science": "SCIENCE_HOLD",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["417", "941"], required=True)
    parser.add_argument("--status", type=Path, required=True)
    args = parser.parse_args()
    try:
        proof = validate(json.loads(args.status.read_text(encoding="utf-8")), args.case)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("PUBLIC_P3_B_COMPLETION_GATE=HOLD", type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(proof, sort_keys=True))
    return 0 if proof["b_p3"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
