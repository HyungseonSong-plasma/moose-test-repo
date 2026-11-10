#!/usr/bin/env python3
"""Validate public-only bounded S6 B diagnostic evidence without asserting P3 success."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

EXPECTED_SOURCE = "29d1acc6ef7969908b86719e4b95c73a1565136d"
EXPECTED_CANDIDATE = "bebaf47a33ff5ee1d6b933d9691bf48f5ec0f947"
EXPECTED_OCI = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"


def validate(report: dict, case: str) -> dict:
    if case not in ("417", "941") or report.get("case") != case:
        raise ValueError("DIAGNOSTIC_CASE_MISMATCH")
    if report.get("schema") != "issue493_public_p3_native_v2" or report.get("mode") != "diagnostic":
        raise ValueError("DIAGNOSTIC_SCHEMA_OR_MODE")
    if (report.get("source_sha") != EXPECTED_SOURCE
            or report.get("candidate_sha") != EXPECTED_CANDIDATE
            or report.get("oci_image") != EXPECTED_OCI):
        raise ValueError("DIAGNOSTIC_PIN_MISMATCH")
    if any(report.get(x) != "PASS" for x in ("P0", "P1")):
        raise ValueError("DIAGNOSTIC_P0_P1_NOT_PROVEN")
    if (report.get("P2") != "HOLD" or report.get("P3") != "HOLD"
            or report.get("P4") != "NOT_RUN"
            or report.get("science") != "SCIENCE_HOLD"):
        raise ValueError("DIAGNOSTIC_FALSE_COMPLETION")
    arms = report.get("variants", {})
    b, c = arms.get("B", {}), arms.get("C", {})
    if (b.get("P2") != "PASS" or b.get("P3") not in ("PASS", "FAIL", "HOLD")
            or c.get("P2") != "NOT_RUN" or c.get("P3") != "NOT_RUN"
            or report.get("p2_passed_arms") != ["B"]
            or report.get("p2_not_run_arms") != ["C"]):
        raise ValueError("DIAGNOSTIC_B_C_GUARD")
    if b.get("timeout_budget_seconds") != 600 or not isinstance(b.get("wall_seconds"), (int, float)):
        raise ValueError("DIAGNOSTIC_TIMEOUT_BUDGET")
    if b["wall_seconds"] < 0 or b["wall_seconds"] > 690:
        raise ValueError("DIAGNOSTIC_WALL_TIME_BOUND")
    for key in ("last_reported_step", "heartbeat_samples", "native_log_bytes"):
        value = b.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("DIAGNOSTIC_NUMERIC_TELEMETRY")
    if b.get("timed_out"):
        if b.get("exit_code") is not None or b.get("termination") != "TIMEOUT":
            raise ValueError("DIAGNOSTIC_TIMEOUT_EXIT_CODE")
        if b.get("reason") != "P3_DIAGNOSTIC_BUDGET_END":
            raise ValueError("DIAGNOSTIC_TIMEOUT_REASON")
    if b.get("P3") == "PASS" and b.get("frames") != 461:
        raise ValueError("DIAGNOSTIC_FALSE_B_COMPLETION")
    return {
        "event": "PUBLIC_P3_B_DIAGNOSTIC_VALIDATED",
        "case": case,
        "b_status": b["P3"],
        "b_reason": b.get("reason"),
        "p2": "B_PASS_C_NOT_RUN",
        "p3": "HOLD",
        "p4": "NOT_RUN",
        "science": "SCIENCE_HOLD",
        "elapsed_seconds": b.get("wall_seconds"),
        "last_reported_step": b.get("last_reported_step"),
        "heartbeat_samples": b.get("heartbeat_samples"),
        "max_observed_memory_bytes": b.get("max_observed_memory_bytes"),
        "max_observed_cpu_percent": b.get("max_observed_cpu_percent"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["417", "941"], required=True)
    parser.add_argument("--status", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = json.loads(args.status.read_text(encoding="utf-8"))
        safe = validate(report, args.case)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("PUBLIC_P3_B_DIAGNOSTIC_GATE=HOLD", type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(safe, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
