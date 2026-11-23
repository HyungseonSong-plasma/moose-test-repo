#!/usr/bin/env python3
"""P6-D4: Public D -> generated Physics Chemistry/Continuity/Energy, original 100-row e lookup.

Only an exact P3-X/P4-X 11-layer *disposable* S6 case may be converted.
The original 100-row Electron Lookup table is immutable, is never substituted
with the New-only 42-row reference, and is rehashed both before and after
staging. Native P2, P05, RF/D8 and science are separate executable gates.
This intentionally offers NO historical Public D compatibility runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re

from prepare_s6_newonly import JSON_SHA, TEMPLATE_SHA, ELECTRON_MOMENTS_SHA
from retire_s6_p4_duplicate_owners import C0, AFTER_SHA

REPO = Path(__file__).resolve().parents[3]
PILOT = REPO / "experiments" / "Issue402_plasma_dsl_g1"
CASE_IDS = ("417", "941")
ORIGINAL_TABLE = REPO / "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
ORIGINAL_TABLE_SHA256 = "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
ORIGINAL_TABLE_GIT_BLOB = "bedcaf17fb3ef93ba8973cc6b32aa6e783e2292a"
EXPECTED_IONS = {
    "O2p": (1, 0.032),
    "Om": (-1, 0.016),
    "Op": (1, 0.016),
}
EXPECTED_REACTIONS = {"EI-02", "EI-17", "EI-415", "EI-401", "EI-407", "EI-2069", "H25"}
E_TRANSPORT = {
    "type": "lookup",
    "file": "../../Issue91_real_qvt_r3/r3_e0/electron_moments.txt",
    "unit": "reduced",
    "bounds_policy": "clamp",
}
ION_TRANSPORT = {
    "type": "constant", "file": "none", "unit": "physical",
    "mobility": 10, "diffusivity": 0.25851999786435537,
}
LAYER_RE = re.compile(r"(?m)^  \[([A-Za-z0-9_]+)\]\s*$")
VARIABLE_RE = re.compile(r"(?m)^    variable\s*=\s*(log_O2p|log_Om|log_Op)\s*$")


class PublicDHold(ValueError):
    """A Public D physics contract was not proved; no legacy fallback."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked(path: Path, expected: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PublicDHold("PUBLIC_D_MISSING_OR_SYMLINK_" + label)
    blob = path.read_bytes()
    if sha(blob) != expected:
        raise PublicDHold("PUBLIC_D_SHA_MISMATCH_" + label)
    return blob


def check_100row_table(source: Path) -> bytes:
    blob = checked(source, ORIGINAL_TABLE_SHA256, "ORIGINAL_100ROW_ELECTRON_LOOKUP")
    rows = blob.decode("utf-8").splitlines()
    if len(rows) != 100:
        raise PublicDHold("PUBLIC_D_100ROW_LOOKUP_CARDINALITY")
    x: list[float] = []
    for row in rows:
        values = row.split()
        if len(values) != 3:
            raise PublicDHold("PUBLIC_D_LOOKUP_EXPECTS_THREE_COLUMNS")
        nums = [float(value) for value in values]
        if not all(math.isfinite(v) and v > 0 for v in nums):
            raise PublicDHold("PUBLIC_D_LOOKUP_NONPHYSICAL")
        x.append(nums[0])
    if any(b <= a for a, b in zip(x, x[1:])):
        raise PublicDHold("PUBLIC_D_LOOKUP_NONMONOTONIC_ENERGY")
    if x[0] != 1.40991 or x[-1] != 22.1378:
        raise PublicDHold("PUBLIC_D_LOOKUP_ENDPOINTS_DRIFT")
    return blob


def check_mechanism(case: str, document: dict) -> None:
    if case not in CASE_IDS:
        raise PublicDHold("PUBLIC_D_UNSUPPORTED_S6_CASE")
    if set(document) != {
        "species", "equations", "reactions", "ion_surface_current",
        "drift_diffusion_boundaries",
    }:
        raise PublicDHold("PUBLIC_D_NEW_PHYSICS_SCHEMA_REQUIRED")
    species = document["species"]
    if set(species) != {"e", "O2", "O", "O2p", "Om", "Op", "O2a"}:
        raise PublicDHold("PUBLIC_D_SEVEN_SPECIES_REQUIRED")
    if species["e"].get("charge_number") != -1 or species["e"].get("transport_coef") != E_TRANSPORT:
        raise PublicDHold("PUBLIC_D_ORIGINAL_ELECTRON_LOOKUP_POLICY_DRIFT")
    for name, (charge, mass) in EXPECTED_IONS.items():
        ion = species[name]
        if (ion.get("charge_number") != charge or ion.get("molar_mass") != mass
                or ion.get("transport_coef") != ION_TRANSPORT):
            raise PublicDHold("PUBLIC_D_ION_COEFFICIENT_OR_CHARGE_DRIFT_" + name)
    if (set(document["equations"]) != EXPECTED_REACTIONS | {"EI-" + case}
            or len(document["reactions"]) != 8
            or {item.get("id") for item in document["reactions"]} != set(document["equations"])):
        raise PublicDHold("PUBLIC_D_CHEMISTRY_8_REACTIONS_REQUIRED")
    if document["ion_surface_current"] != {"electron_wall_number_flux": "e_wall_number_flux"}:
        raise PublicDHold("PUBLIC_D_WALL_CURRENT_CONTRACT_DRIFT")
    if set(document["drift_diffusion_boundaries"]) != {
        "inlet outlet", "plasma_electrode plasma_metal plasma_right",
        "plasma_cover", "plasma_wafer", "plasma_focus_ring",
    }:
        raise PublicDHold("PUBLIC_D_ION_WALL_BOUNDARIES_DRIFT")


def stage_public_d_physics(
    folder: Path, case: str, ordered: list[str],
    original_table: Path = ORIGINAL_TABLE,
) -> dict:
    """Retain already verified New-only 26->0/10->0/6->0 source handoff.

    Rewrite only the disposable staged e-table to the original 100-row bytes
    and bind a distinct Public D mechanism name, keeping Chemistry generated.
    This never reads or uses a historical Public D P2 compatibility runner.
    """
    if case not in CASE_IDS:
        raise PublicDHold("PUBLIC_D_UNKNOWN_CASE")
    folder = Path(folder).resolve(strict=True)
    if folder.name != "Issue395_powered_chemistry_ladder" or folder.parent.name != "experiments":
        raise PublicDHold("PUBLIC_D_NOT_DISPOSABLE_CASE_DIR")
    marker = folder / ".issue633_disposable_scratch"
    if marker.is_symlink() or not marker.is_file() or marker.read_text().strip() != "issue633-scratch-only":
        raise PublicDHold("PUBLIC_D_SCRATCH_MARKER_MISSING")
    if len(ordered) != 11 or len({Path(s).name for s in ordered}) != 11:
        raise PublicDHold("PUBLIC_D_EXPECT_EXACT_11_LAYERS")
    names = [Path(s).name for s in ordered]
    if names[0] != C0 or names[-1] != "migrated_continuity.i":
        raise PublicDHold("PUBLIC_D_STAGED_ORDER_DRIFT")
    if any(not n.endswith(".i") or not (folder / n).is_file()
           or (folder / n).is_symlink() for n in names):
        raise PublicDHold("PUBLIC_D_STAGED_LAYER_MISSING")
    original_layers = {name: sha((folder / name).read_bytes()) for name in names}
    checked(folder / C0, AFTER_SHA, "P4X_EXACT_SINGLE_OWNER_C0")
    # The consumer graph may validly reference ions outside FV equations.
    # Only the old Native ion FVKernel/FVBC objects are forbidden; preserve
    # density/Poisson/diagnostic auxiliary consumers unchanged.
    from retire_s6_ion_fv_owners import BLOCK, ROOT as SECTION
    for name in names:
        source = (folder / name).read_text(encoding="utf-8")
        for match in BLOCK.finditer(source):
            if not VARIABLE_RE.search(match.group("body")):
                continue
            roots = [r.group(1) for r in SECTION.finditer(source[:match.start()])]
            if roots and roots[-1] in ("FVKernels", "FVBCs"):
                raise PublicDHold("PUBLIC_D_OLD_NATIVE_ION_FV_OWNER_REMAINS_" + match.group("name"))

    chemistry = folder / "chemistry"
    newonly_json = chemistry / ("unified_s6_" + case + "_newonly.json")
    newonly_template = PILOT / ("issue633_newonly_s6_" + case + "_continuity.template.i")
    source_json = PILOT / "chemistry" / newonly_json.name
    template = checked(newonly_template, TEMPLATE_SHA[case], "NEW_PHYSICS_TEMPLATE")
    original_mechanism = checked(newonly_json, JSON_SHA[case], "PINNED_8_REACTION_MECHANISM")
    checked(source_json, JSON_SHA[case], "REPOSITORY_8_REACTION_MECHANISM")
    mechanism = json.loads(original_mechanism)
    check_mechanism(case, mechanism)
    template_text = template.decode("utf-8")
    old_binding = "files = 'chemistry/" + newonly_json.name + "'"
    new_name = "public_d_s6_" + case + "_physics.json"
    if (template_text.count(old_binding) != 1 or
            template_text.count("[Chemistry]") != 1 or
            template_text.count("[Continuity]") != 1 or
            template_text.count("[Energy]") != 1 or
            "fvm_species = 'O2p Om Op'" not in template_text or
            "transport_coefficient = fluid" not in template_text):
        raise PublicDHold("PUBLIC_D_PHYSICS_CHEMISTRY_SOURCE_OWNER_MISSING")

    target_table = (chemistry / E_TRANSPORT["file"]).resolve()
    required_target = folder.parent / "Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
    if target_table != required_target.resolve() or target_table.is_symlink():
        raise PublicDHold("PUBLIC_D_ELECTRON_TABLE_PATH_DRIFT")
    checked(target_table, ELECTRON_MOMENTS_SHA, "PRIOR_NEWONLY_42ROW_TABLE")
    if Path(original_table).resolve() == target_table:
        raise PublicDHold("PUBLIC_D_SOURCE_TABLE_MUST_REMAIN_IMMUTABLE")
    bytes_100 = check_100row_table(Path(original_table))
    target_json = chemistry / new_name
    if target_json.exists() or target_json.is_symlink():
        raise PublicDHold("PUBLIC_D_CANNOT_OVERWRITE_EXISTING_OUTPUT")

    # No original or generated source file has changed. All checks precede
    # any mutation, and this function writes only into disposable Scratch.
    changed_overlay = template_text.replace(old_binding, "files = 'chemistry/" + new_name + "'")
    overlay = folder / "migrated_continuity.i"
    before_overlay = sha(overlay.read_bytes())
    if before_overlay != TEMPLATE_SHA[case]:
        raise PublicDHold("PUBLIC_D_NEWONLY_OVERLAY_SHA_DRIFT")
    target_table.write_bytes(bytes_100)
    target_json.write_bytes(original_mechanism)
    overlay.write_text(changed_overlay, encoding="utf-8")
    if (sha(target_table.read_bytes()) != ORIGINAL_TABLE_SHA256 or
            sha(target_json.read_bytes()) != JSON_SHA[case] or
            sha(overlay.read_bytes()) != sha(changed_overlay.encode("utf-8"))):
        raise PublicDHold("PUBLIC_D_POSTWRITE_READBACK_FAILED")
    for name in names[:-1]:
        if sha((folder / name).read_bytes()) != original_layers[name]:
            raise PublicDHold("PUBLIC_D_UNAUTHORIZED_LAYER_MODIFICATION_" + name)
    return {
        "schema": "issue672.public_d_generated_physics_100row.v1",
        "case": case, "mode": "PUBLIC_D_NEW_PHYSICS_CHEMISTRY_ONLY",
        "history_compat_runner": "NOT_CREATED",
        "disposable_only": True,
        "original_table_sha256": ORIGINAL_TABLE_SHA256,
        "original_table_rows": 100, "newonly_42row_replaced_in_scratch": True,
        "json_sha256": sha(target_json.read_bytes()), "json_name": new_name,
        "overlay_sha256": sha(overlay.read_bytes()),
        "original_11layer_sha256": original_layers,
        "staged_11layer_sha256": {n: sha((folder / n).read_bytes()) for n in names},
        "expected_physics_ion_kernel_count": 12,
        "expected_physics_ion_bc_count": 12,
        "expected_electron_sheath_bc_count": 8,
        "chemistry_reaction_count": 8,
        "ion_native_owner_retirement": "REQUIRES_PRIOR_PINNED_P2_26_TO_0_AND_P4X_C0",
        "P2": "NOT_RUN", "P3": "NOT_RUN", "P4": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", choices=CASE_IDS, required=True)
    ap.add_argument("--folder", type=Path, required=True)
    ap.add_argument("--ordered", type=Path, required=True,
                    help="JSON list of eleven staged input paths, last=overlay")
    ap.add_argument("--original-table", type=Path, default=ORIGINAL_TABLE)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()
    try:
        result = stage_public_d_physics(
            args.folder, args.case,
            json.loads(args.ordered.read_text()), args.original_table)
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        if args.receipt.exists():
            raise PublicDHold("PUBLIC_D_REFUSE_RECEIPT_OVERWRITE")
        args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("PUBLIC_D_100ROW_PHYSICS_STAGE_PASS", args.case,
              result["original_table_sha256"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print("PUBLIC_D_100ROW_PHYSICS_STAGE_HOLD", type(e).__name__, str(e))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
