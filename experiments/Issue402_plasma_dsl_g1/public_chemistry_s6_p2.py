#!/usr/bin/env python3
"""Scratch-only Native P2 for actual archived S6 chemistry source cutover.

Uses the public S6 historical staging contract and an exact-head PhysicsApp
binary. Never executes a timestep or reads/publishes private kinetic tables.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

PILOT = Path(__file__).resolve().parent
ROOT = PILOT.parents[1]
sys.path.insert(0, str(PILOT))
import public_option_s6_p2 as option
from chemistry.prepare_s6_run_input import prepare


def execute(historical: Path, binary: Path, source_sha: str, evidence: Path) -> dict:
    identity = option.check_source(source_sha, historical, binary)
    reference = option.p2.preflight(ROOT)
    if reference.get("P0") != "PASS":
        raise ValueError("Historical public S6 preflight must PASS")
    manifest = json.loads((ROOT / option.p2.DECKS / "manifest.json").read_text())
    evidence.mkdir(parents=True, exist_ok=True)
    report = {
        "gate": "issue402_s6_chemistry_cutover_native_p2",
        "source_sha": source_sha,
        "binary_sha256": identity["binary_sha256"],
        "science": "SCIENCE_HOLD",
        "P3": "NOT_RUN",
        "status": "HOLD",
        "cases": {}
    }
    with tempfile.TemporaryDirectory(prefix="issue402_chemistry_cutover_p2_",
                                     dir=os.getenv("RUNNER_TEMP", None)) as scratch:
        for variant in ("417", "941"):
            staged = Path(scratch) / variant
            # Use the verified C candidate that removes only original ne_transport.
            ordered = option.p2.stage(ROOT, historical, variant, "C", staged, manifest)
            chemistry_dir = staged / option.p2.CHEM
            canonical = option.canonicalize_staged_D_inputs(chemistry_dir, ordered)
            type_remap = option.remap_staged_fem_types(chemistry_dir, ordered)
            cutover = prepare(chemistry_dir, ordered, variant)
            log = evidence / f"s6_{variant}_chemistry_cutover_p2.log"
            verdict = option.run_one(binary, identity["binary_sha256"],
                                     staged, ordered, log, 1200)
            report["cases"][variant] = {
                **verdict,
                "source_cutover": cutover,
                "scratch_canonical_state_renames": canonical,
                "scratch_fem_type_remap": type_remap
            }
            (evidence / "issue402_s6_chemistry_cutover_p2.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n")
    report["status"] = "P2_PASS_ONLY" if all(
        case["P2"] == "PASS" for case in report["cases"].values()) else "HOLD"
    (evidence / "issue402_s6_chemistry_cutover_p2.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = execute(args.historical.resolve(), args.binary.resolve(),
                         args.expected_head, args.evidence.resolve())
    except Exception as exception:
        result = {"gate": "issue402_s6_chemistry_cutover_native_p2",
                  "status": "HOLD", "P3": "NOT_RUN", "science": "SCIENCE_HOLD",
                  "reason": str(exception)[:500]}
        args.evidence.mkdir(parents=True, exist_ok=True)
        (args.evidence / "issue402_s6_chemistry_cutover_p2.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "P2_PASS_ONLY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
