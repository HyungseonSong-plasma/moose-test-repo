#!/usr/bin/env python3
"""Fail-closed two-case native 100us evidence summary, never science parity."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

from issue652_g6b_parallel_evidence import (
    SOURCE_100_SHA, ParallelEvidenceHold, load, sha, verify_bundle,
)

CASES = ("417", "941")


def validate_case(entry: dict, case: str, source_sha: str,
                  manifest_sha: str, binary_sha: str) -> dict:
    grid = entry.get("original_time_grid", {})
    series = entry.get("time_series", {})
    csv = entry.get("native_csv", {})
    exodus = entry.get("native_exodus", {})
    solver = entry.get("solver", {})
    if (
        entry.get("schema") != "issue652.g6b.native_100us_case.v1"
        or entry.get("source_sha") != source_sha
        or entry.get("case_id") != case
        or entry.get("build_manifest_sha256") != manifest_sha
        or entry.get("binary_sha256") != binary_sha
        or entry.get("original_publicd_lookup_sha256") != SOURCE_100_SHA
        or entry.get("P1") != "PASS"
        or entry.get("P2") != "PASS_TYPED_15_OWNERS"
        or entry.get("P3_100us") != "PASS_NATIVE_FINITE_461_FRAMES"
        or entry.get("P4") != "NOT_RUN"
        or entry.get("science") != "SCIENCE_HOLD"
        or entry.get("conservation") != "UNVERIFIED"
        or entry.get("raw_protected_rates_in_artifact") is not False
        or entry.get("native_solver_log_in_artifact") is not False
        or entry.get("native_input_deck_in_artifact") is not False
        or entry.get("original_s6_input_unchanged") is not True
        or entry.get("public_outputs_ready") is not True
        or grid.get("time_points") != 461
        or grid.get("intervals") != 460
        or grid.get("end_time_seconds") != 1e-4
        or grid.get("scheme") != "implicit-euler"
        or grid.get("checkpoint") is not True
        or series.get("status") != "PASS_NATIVE_FINITE_EXACT_461_TIME_POINTS"
        or series.get("time_points") != 461
        or series.get("intervals") != 460
        or series.get("t0_seconds") != 0.0
        or not isinstance(series.get("t_end_seconds"), (int, float))
        or not math.isfinite(series["t_end_seconds"])
        or abs(series["t_end_seconds"] - 1e-4) > 1e-15
        or series.get("charge_conservation_budget") != "NOT_EVALUATED"
        or series.get("semantic_parity") != "NOT_EVALUATED"
        or solver.get("status") != "EXIT_ZERO"
        or solver.get("exit_code") != 0
        or exodus.get("format_header_verified") is not True
        or exodus.get("nodal_field_parity") != "NOT_EVALUATED"
    ):
        raise ParallelEvidenceHold("FULL100_CASE_SCOPE_OR_COMPLETION_NOT_PROVEN:" + case)
    for item in (csv, exodus):
        if (not re.fullmatch(r"[a-f0-9]{64}", str(item.get("sha256", "")))
                or type(item.get("bytes")) is not int or item["bytes"] <= 0):
            raise ParallelEvidenceHold("FULL100_OUTPUT_HASH_ABSENT:" + case)
    return {
        "case_id": case, "status": "PASS_NATIVE_FINITE_461_FRAMES",
        "source_sha": source_sha, "build_manifest_sha256": manifest_sha,
        "csv_sha256": csv["sha256"], "csv_bytes": csv["bytes"],
        "exodus_sha256": exodus["sha256"], "exodus_bytes": exodus["bytes"],
        "frame_count": 461, "end_time_s": 1e-4,
        "conservation": "UNVERIFIED", "scientific_parity": "UNVERIFIED",
    }


def aggregate(folder: Path, manifest_path: Path,
              source_sha: str, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ParallelEvidenceHold("AGGREGATE_REFUSE_OVERWRITE")
    manifest = verify_bundle(manifest_path, source_sha)
    manifest_sha = sha(manifest_path)
    case_evidence = {}
    for case in CASES:
        entry = load(folder / ("g6b-full100-" + case + ".json"))
        case_evidence[case] = validate_case(
            entry, case, source_sha, manifest_sha,
            manifest["files"]["physics_app/physics-opt"])
    result = {
        "schema": "issue652.g6b.full100_parallel_summary.v1",
        "source_sha": source_sha, "build_manifest_sha256": manifest_sha,
        "original_publicd_lookup_sha256": SOURCE_100_SHA,
        "cases": case_evidence,
        "P1": "PASS_SHARED_BINARY_TWO_RUNNERS",
        "P2": "PASS_TYPED_15_GENERATED_OWNERS_EACH",
        "P3_100us": "PASS_NATIVE_461_TIMES_EACH_NO_PARITY",
        "P4": "NOT_RUN", "conservation": "UNVERIFIED",
        "scientific_equivalence": "UNVERIFIED", "science": "SCIENCE_HOLD",
        "protected_rate_artifacts": False,
        "main_merge": "NOT_AUTHORIZED",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.receipts, args.manifest, args.source_sha, args.output)
    print("G6B_FULL100_BOTH_INDEPENDENT_461_FRAME_NATIVE_PASS", "SCIENCE_HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
