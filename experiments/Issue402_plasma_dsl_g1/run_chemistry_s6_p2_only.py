#!/usr/bin/env python3
"""Prepare and validate active Native S6 Chemistry input stacks without P3.

Prerequisites (external to this command):
- exact committed PhysicsApp HEAD already built as physics_app/physics-opt;
- same-job native_p1_identity.json and native_build.log from P1;
- public unpacked Issue493 S6 P2 decks and pinned historical checkout;
- no protected/private-rate directory in the historical source.

This command stages the ten historical C input layers + one Chemistry overlay
into durable, operator-reviewable scratch copies, removes exclusively proven
obsolete D1 debug observers and runs --check-input ONLY.
It never calls run_canonical_s6_p3_once.run, never executes a time step, and
never publishes/merges a science result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import public_option_s6_p2 as option
from chemistry.prepare_s6_run_input import prepare
from p3_chemistry_preflight import audit

ROOT = Path(__file__).resolve().parents[2]
CASES = ("417", "941")
D_BASE = ROOT / "experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_only(historical: Path, expected_head: str, output: Path,
               cases: tuple[str, ...], timeout_seconds: int = 1200) -> dict:
    historical = historical.resolve()
    output = output.resolve()
    if output.exists():
        raise ValueError("P2_REPORT_DIRECTORY_ALREADY_EXISTS")
    if timeout_seconds < 1:
        raise ValueError("P2_TIMEOUT_MUST_BE_POSITIVE")
    if not cases or any(case not in CASES for case in cases) or len(set(cases)) != len(cases):
        raise ValueError("P2_CASES_MUST_BE_UNIQUE_417_OR_941")
    # Static mechanism gate never grants P3 authorization.
    static = audit(ROOT)
    if static["status"] != "STATIC_INPUTS_READY_P3_NOT_AUTHORIZED":
        raise ValueError("CHEMISTRY_S6_STATIC_GATE_FAILED")
    public_preflight = option.p2.preflight(ROOT)
    if public_preflight.get("P0") != "PASS":
        raise ValueError("P2_PUBLIC_S6_PREFLIGHT_NOT_PASS")
    binary = ROOT / "physics_app/physics-opt"
    identity = option.check_source(expected_head, historical, binary)
    manifest = json.loads(
        (ROOT / option.p2.DECKS / "manifest.json").read_text(encoding="utf-8"))
    result = {
        "schema": "issue402_chemistry_s6_native_p2_only_v1",
        "source_sha": expected_head,
        "binary_sha256": identity["binary_sha256"],
        "historical_sha": identity["historical_sha"],
        "oci_image": identity["build_image"],
        "cases": {},
        "P0": "PASS",
        "P1": "PASS_SOURCE_BOUND_BINARY",
        "P2": "HOLD",
        "native_input_scope": "ACTIVE_S6_PHYSICS_WITH_OBSOLETE_D1_DEBUG_RETIRED",
        "retired_d1_diagnostic_parity": "NOT_APPLICABLE",
        "retired_d1_independent_review": "NOT_REQUIRED_BY_OPERATOR",
        "P3": "NOT_RUN",
        "P4": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }
    output.mkdir(parents=True, exist_ok=False)
    try:
        for case in cases:
            folder = output / ("S6-" + case)
            folder.mkdir()
            staged = folder / "scratch"
            # Canonical D base was prepared once from the pinned source deck.
            # Never stage retired issue397 diagnostics just to delete them.
            ordered = option.p2.stage(
                ROOT, historical, case, "C", staged, manifest,
                d_base_source=D_BASE)
            chemistry = staged / option.p2.CHEM
            migration = option.canonicalize_staged_D_inputs(chemistry, ordered)
            type_remap = option.remap_staged_fem_types(chemistry, ordered)
            cutover = prepare(chemistry, ordered, case)
            overlay = chemistry / "migrated_continuity.i"
            if digest(overlay) != cutover["overlay_sha256"]:
                raise ValueError("P2_CHEMISTRY_OVERLAY_CONTENT_CHANGED")
            # No implicit JSON DD transport cutover: original S6 Native ion
            # coefficients and Poisson owner remain exactly as staged.
            if not all((staged / relative).is_file() for relative in ordered):
                raise ValueError("P2_S6_STAGED_INPUT_LAYER_MISSING")
            if digest(binary) != identity["binary_sha256"]:
                raise ValueError("P2_NATIVE_BINARY_CHANGED_AFTER_P1")
            checked = option.run_one(
                binary, identity["binary_sha256"], staged, ordered,
                folder / "native_P2.log", timeout_seconds)
            result["cases"][case] = {
                "P2": checked["P2"],
                "check_input": checked,
                "staged_inputs": ordered,
                "scratch_canonicalization": migration,
                "scratch_fem_type_remap": type_remap,
                "scratch_chemistry_cutover": cutover,
                "overlay_sha256": digest(overlay),
                "P3": "NOT_RUN",
            }
            if checked["P2"] != "PASS":
                raise ValueError("P2_S6_" + case + "_CHECK_INPUT_FAILED")
        result["P2"] = "PASS"
        return result
    finally:
        # Durable evidence is written even if the first or second case fails.
        (output / "readiness.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=("both", "417", "941"), default="both")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()
    cases = CASES if args.case == "both" else (args.case,)
    report = check_only(args.historical, args.expected_head,
                        args.output, cases, args.timeout_seconds)
    print(json.dumps({
        "P2": report["P2"],
        "P3": report["P3"],
        "source_sha": report["source_sha"],
        "cases": {k: v["P2"] for k, v in report["cases"].items()},
        "readiness": str(args.output / "readiness.json"),
    }, sort_keys=True))
    return 0 if report["P2"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
