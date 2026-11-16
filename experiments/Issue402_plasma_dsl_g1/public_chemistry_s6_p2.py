#!/usr/bin/env python3
"""Scratch-only Native P2 for actual archived S6 chemistry source cutover.

Uses the public S6 historical staging contract and an exact-head PhysicsApp
binary. Never executes a timestep or reads/publishes private kinetic tables.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

PILOT = Path(__file__).resolve().parent
ROOT = PILOT.parents[1]
sys.path.insert(0, str(PILOT))
import public_option_s6_p2 as option
from chemistry.prepare_s6_run_input import prepare
from chemistry.prepare_hybrid_json_s6 import (
    OLD_SHEATH_TYPES, migrate_exact_s6_fem_sheath,
)


def rebind_staged_chemistry_sheath_bcs(chemistry_dir: Path,
                                      ordered: list[str]) -> dict:
    """Reuse the eight-owner hybrid BC identity contract on disposable P2 only.

    Chemistry.prepare() already normalizes log_e/log_e_energy and the two wall
    Functor names. The archived B/D decks and any P3 science are unchanged.
    """
    names = [Path(item).name for item in ordered]
    if (len(names) != 11 or names[-1] != "migrated_continuity.i"
            or len(set(names)) != 11
            or any(name != item.split("/")[-1] or not item.endswith(".i")
                   for name, item in zip(names, ordered))):
        raise ValueError("S6_CHEM_SHEATH_UNEXPECTED_LAYER_SET")
    base = chemistry_dir / names[0]
    old_types = tuple(OLD_SHEATH_TYPES.values())
    for name in names[1:]:
        content = (chemistry_dir / name).read_text(encoding="utf-8")
        if any(re.search(r"(?m)^    type\s*=\s*" + re.escape(kind) + r"\s*$",
                         content) for kind in old_types):
            raise ValueError("S6_CHEM_SHEATH_SECONDARY_OWNER_" + name)
    original = base.read_text(encoding="utf-8")
    revised, owners = migrate_exact_s6_fem_sheath(original)
    if revised == original or len(owners) != 8:
        raise ValueError("S6_CHEM_SHEATH_EIGHT_OWNER_REBIND_REQUIRED")
    # Fail-closed all signatures before the sole scratch write.
    base.write_text(revised, encoding="utf-8")
    if base.read_text(encoding="utf-8") != revised:
        raise ValueError("S6_CHEM_SHEATH_STAGED_READBACK_FAILED")
    return {
        "status": "SCRATCH_ONLY_EXACT_EIGHT_REGISTERED_SHEATH_BCS",
        "source_layer": names[0],
        "owner_count": len(owners),
        "owners": owners,
        "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "staged_sha256": hashlib.sha256(revised.encode("utf-8")).hexdigest(),
        "P3": "NOT_RUN", "science": "SCIENCE_HOLD",
    }


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
            # D starts from a prebuilt C0 physics base, never a historical
            # debug-instrumented C deck followed by probe removal.
            d_base = (PILOT / "native/s6_c0_physics_base_no_d1.i")
            ordered = option.p2.stage(
                ROOT, historical, variant, "C", staged, manifest,
                d_base_source=d_base)
            chemistry_dir = staged / option.p2.CHEM
            canonical = option.canonicalize_staged_D_inputs(chemistry_dir, ordered)
            type_remap = option.remap_staged_fem_types(chemistry_dir, ordered)
            cutover = prepare(chemistry_dir, ordered, variant)
            sheath_cutover = rebind_staged_chemistry_sheath_bcs(
                chemistry_dir, ordered)
            log = evidence / f"s6_{variant}_chemistry_cutover_p2.log"
            verdict = option.run_one(binary, identity["binary_sha256"],
                                     staged, ordered, log, 1200)
            report["cases"][variant] = {
                **verdict,
                "source_cutover": cutover,
                "scratch_canonical_state_renames": canonical,
                "scratch_fem_type_remap": type_remap,
                "scratch_sheath_bc_cutover": sheath_cutover,
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
