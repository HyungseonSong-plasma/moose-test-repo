#!/usr/bin/env python3
"""#652 G8 paired real-S6 *same-physics* Old/New Poisson source-stage gate.

Old = exact historical P4 C0 native 15 Poisson/charge owners + old overlay.
New = exact G5 C0 with those same 15 removed + generated [Poisson] Action.
Both use the exact same 26e84a4 PhysicsApp ELF/OCI, mesh, ion/electron chemistry,
reaction tables, 400W boundary input, time stepper and Public D original 100-row
lookup. The ONLY approved input differences are C0, the overlay and removal of
the JSON 'poisson' selector in Old (legacy route). Static scope, no native run.

Must be called with two independently copied P3-X disposable scratch trees.
Never alters originals, inputs outside disposable scratch, or private EI data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CHEM = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry"
sys.path.insert(0, str(CHEM))
from prepare_s6_newonly import JSON_SHA, TEMPLATE_SHA  # noqa: E402
from retire_s6_p4_duplicate_owners import (  # noqa: E402
    AFTER_SHA as OLD_C0_SHA, C0, retire_p4_duplicate_owners,
)
from retire_s6_poisson_charge_owners import (  # noqa: E402
    G5_OUTPUT_C0_SHA, G5_OVERLAY_SHA, TARGET_SHA,
)
from poisson_contract import parse_strict_json, validate_poisson  # noqa: E402
from issue652_g6b_publicd100_stage import (  # noqa: E402
    PUBLIC_D_100_SHA256, OLD_42_SHA256, SOURCE_100,
    TABLE_RELATIVE, CHEM_RELATIVE, time_contract,
)
from issue652_g5_native_p2 import file_sha

SOURCE_SHA = "26e84a4a33cf93d9e278a4f0b2d78c53cae2d6ce"
CASES = ("417", "941")
ROOT_ALLOWED_CHANGES = (
    C0,
    "migrated_continuity.i",
    "chemistry/unified_s6_{case}_newonly.json",
)


class MatchedHold(ValueError):
    pass


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def checkout_sha() -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
        timeout=10).strip()


def files_under(folder: Path) -> dict[str, str]:
    if folder.is_symlink() or not folder.is_dir():
        raise MatchedHold("UNSAFE_PUBLIC_CASE_ROOT")
    found = {}
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise MatchedHold("CASE_TREE_SYMLINK_DENIED")
        if path.is_file():
            found[path.relative_to(folder).as_posix()] = file_sha(path)
    return found


def diff_allowed(old: dict[str, str], new: dict[str, str], case: str) -> dict:
    allowed = {
        (CHEM_RELATIVE / item.format(case=case)).as_posix()
        for item in ROOT_ALLOWED_CHANGES
    }
    if set(old) != set(new):
        raise MatchedHold("OLD_NEW_FILE_INVENTORY_DRIFT")
    changed = {path for path in old if old[path] != new[path]}
    if changed != allowed:
        raise MatchedHold("UNAUTHORIZED_CASE_INPUT_DIFFERENCE:" +
                          ",".join(sorted(changed.symmetric_difference(allowed)))[:180])
    return {
        "allowed_changed_paths": sorted(changed),
        "unchanged_file_count": len(old) - len(changed),
        "unchanged_file_manifest_sha256": sha(json.dumps({
            name: digest for name, digest in sorted(old.items())
            if name not in allowed
        }, sort_keys=True, separators=(",", ":")).encode()),
    }


def old_poisson_json(precursor: bytes) -> bytes:
    root = parse_strict_json(precursor)
    validate_poisson(root)
    if set(root) != {"species", "equations", "reactions",
                     "ion_surface_current", "drift_diffusion_boundaries",
                     "poisson"}:
        raise MatchedHold("NEW_MECHANISM_UNEXPECTED_SCHEMA")
    del root["poisson"]
    if set(root) != {"species", "equations", "reactions",
                     "ion_surface_current", "drift_diffusion_boundaries"}:
        raise MatchedHold("LEGACY_JSON_SELECTOR_NOT_EXACTLY_REMOVED")
    return (json.dumps(root, separators=(",", ":"), sort_keys=True,
                       ensure_ascii=True, allow_nan=False) + "\n").encode()


def verify_semantic_json(old_blob: bytes, new_blob: bytes) -> bool:
    old = parse_strict_json(old_blob)
    new = parse_strict_json(new_blob)
    validate_poisson(new)
    if "poisson" in old:
        raise MatchedHold("LEGACY_POISSON_SELECTOR_STILL_ACTIVE")
    changed = dict(new)
    del changed["poisson"]
    if old != changed:
        raise MatchedHold("OLD_NEW_NON_POISSON_JSON_SEMANTICS_DIFFERENT")
    return True


def stage_pair(*, before_g5: Path, after_g5: Path, g5_receipt: Path,
               output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise MatchedHold("REFUSE_OVERWRITE_EXISTING_REPORT")
    if checkout_sha() != SOURCE_SHA:
        raise MatchedHold("EXACT_NATIVE_SOURCE_SHA_NOT_ACTIVE")
    if before_g5.resolve() == after_g5.resolve():
        raise MatchedHold("OLD_NEW_MUST_BE_INDEPENDENT_SCRATCH")
    readiness = json.loads((before_g5 / "readiness.json").read_text())
    new_receipt = json.loads(g5_receipt.read_text())
    if (readiness.get("source_head") != SOURCE_SHA or
            new_receipt.get("source_sha") != SOURCE_SHA or
            set(readiness.get("stage_cases", {})) != set(CASES) or
            set(new_receipt.get("cases", {})) != set(CASES)):
        raise MatchedHold("P3X_G5_SOURCE_IDENTITY_CHANGED")
    original_100 = SOURCE_100.read_bytes()
    if sha(original_100) != PUBLIC_D_100_SHA256:
        raise MatchedHold("PUBLIC_D_ORIGINAL_100ROW_CHANGED")
    results = {}
    for case in CASES:
        before_root = before_g5 / "scratch" / case
        after_root = after_g5 / "scratch" / case
        before_chem = before_root / CHEM_RELATIVE
        after_chem = after_root / CHEM_RELATIVE
        marker = before_chem / ".issue633_disposable_scratch"
        if (marker.is_symlink() or marker.read_text().strip()
                != "issue633-scratch-only"):
            raise MatchedHold("P4_DISPOSABLE_MARKER_REQUIRED")
        record = readiness["stage_cases"][case]
        ordered = [Path(x).name for x in record["ordered"]]
        before_sha = {Path(name).name: file_sha(before_chem / Path(name).name)
                      for name in ordered}
        if (len(ordered) != 11 or ordered[0] != C0
                or ordered[-1] != "migrated_continuity.i"
                or before_sha != record["layer_sha256"]):
            raise MatchedHold("PINNED_PRE_G5_ELEVEN_LAYERS_CHANGED")
        source_json = CHEM / f"unified_s6_{case}_newonly.json"
        new_json_path = after_chem / "chemistry" / source_json.name
        old_json_path = before_chem / "chemistry" / source_json.name
        if (file_sha(source_json) != JSON_SHA[case]
                or file_sha(new_json_path) != JSON_SHA[case]
                or file_sha(old_json_path) != JSON_SHA[case]
                or file_sha(before_chem / ordered[-1]) != TEMPLATE_SHA[case]):
            raise MatchedHold("UNIFIED_POISSON_SOURCE_BEFORE_STAGE_CHANGED")
        mechanism = parse_strict_json(source_json.read_bytes())
        validate_poisson(mechanism)
        p4 = retire_p4_duplicate_owners(
            before_chem, ordered, mechanism,
            post_p3_layer_sha=before_sha,
        )
        if (p4.get("output_c0_sha256") != OLD_C0_SHA or
                file_sha(before_chem / C0) != OLD_C0_SHA):
            raise MatchedHold("HISTORIC_P4_POISSON_C0_SHA_DRIFT")
        old_json_path.write_bytes(old_poisson_json(source_json.read_bytes()))
        if not verify_semantic_json(old_json_path.read_bytes(), new_json_path.read_bytes()):
            raise MatchedHold("OLD_NEW_JSON_SEMANTICS_NOT_EQUAL")
        old_table = before_root / TABLE_RELATIVE
        new_table = after_root / TABLE_RELATIVE
        if (file_sha(old_table) != OLD_42_SHA256 or
                file_sha(new_table) != PUBLIC_D_100_SHA256):
            raise MatchedHold("PUBLIC_D_42_TO_100_STAGE_MISMATCH")
        old_table.write_bytes(original_100)
        if file_sha(old_table) != PUBLIC_D_100_SHA256:
            raise MatchedHold("OLD_PUBLIC_D100_WRITTEN_INCORRECTLY")
        if (file_sha(after_chem / C0) != G5_OUTPUT_C0_SHA or
                file_sha(after_chem / ordered[-1]) != G5_OVERLAY_SHA[case]):
            raise MatchedHold("NEW_G5_15_OWNER_HANDOFF_DRIFT")
        after_details = new_receipt["cases"][case]
        if (after_details["layer_sha256"] != {
                name: file_sha(after_chem / name) for name in ordered}):
            raise MatchedHold("NEW_G5_ELEVEN_LAYERS_RECEIPT_MISMATCH")
        if (after_details["g5"]["retired_poisson_owners"] != 12 or
                after_details["g5"]["retired_charge_owners"] != 3 or
                len(TARGET_SHA) != 15):
            raise MatchedHold("EXACT_15_POISSON_OWNER_DIFFERENCE_NOT_PROVEN")
        old_grid = time_contract((before_chem / C0).read_bytes())
        new_grid = time_contract((after_chem / C0).read_bytes())
        if old_grid != new_grid or old_grid["intervals"] != 460:
            raise MatchedHold("OLD_NEW_100US_TIME_GRID_DIFFERENT")
        inventory = diff_allowed(files_under(before_root),
                                 files_under(after_root), case)
        results[case] = {
            "old_p4_c0_sha256": OLD_C0_SHA,
            "new_g5_c0_sha256": G5_OUTPUT_C0_SHA,
            "old_overlay_sha256": TEMPLATE_SHA[case],
            "new_overlay_sha256": G5_OVERLAY_SHA[case],
            "old_non_poisson_json_sha256": file_sha(old_json_path),
            "new_poisson_json_sha256": JSON_SHA[case],
            "source_equal_except_poisson_owner_contract": "PASS",
            "old_owner_count": 15,
            "new_retired_owner_count": 15,
            "mesh_chemistry_and_rf_inventory": inventory,
            "source_time_grid": old_grid,
            "public_d_lookup_sha256": PUBLIC_D_100_SHA256,
            "legacy_mechanism_excludes_poisson_selector": True,
            "new_mechanism_has_poisson_selector": True,
            "private_ei_in_artifact": False,
        }
    result = {
        "schema": "issue652.g8.old_new_same_input_stage.v1",
        "physics_app_source_sha": SOURCE_SHA,
        "physics_app_binary_identity": "SINGLE_SAME_ELF_REQUIRED_AT_NATIVE",
        "cases": results,
        "only_intended_difference":
            "P4_15_NATIVE_POISSON_CHARGE_OWNERS_VS_G5_GENERATED_ACTION_15",
        "non_poisson_dynamical_input": "SHA_IDENTICAL",
        "same_input_stage": "PASS",
        "native_same_elf_p2": "NOT_RUN",
        "old_new_native_3ns": "NOT_RUN",
        "fieldwise_100us": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("G8_S6_417_941_SAME_INPUT_100ROW_P4_VS_G5_STAGE_PASS", flush=True)
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--before-g5", type=Path, required=True)
    p.add_argument("--after-g5", type=Path, required=True)
    p.add_argument("--g5-receipt", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        stage_pair(before_g5=args.before_g5, after_g5=args.after_g5,
                   g5_receipt=args.g5_receipt, output=args.output)
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        print("G8_MATCHED_STAGE_HOLD", type(exc).__name__, str(exc)[:160], flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
