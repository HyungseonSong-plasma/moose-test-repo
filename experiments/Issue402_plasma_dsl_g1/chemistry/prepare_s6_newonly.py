"""Issue #668: exact-pin disposable New-only Scratch staging; no Native execution.

Call only through prepare_s6_run_input.py --newonly.  Archived inputs, PR
source files, and all source files outside the disposable Scratch are read-only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from retire_s6_ion_fv_owners import CutoverError, retire_in_disposable_scratch
from retire_s6_electron_newonly_owners import (
    inspect_electron_contract, retire_electron_in_disposable_scratch
)
from retire_s6_p4_duplicate_owners import (
    C0 as P4_C0, retire_p4_duplicate_owners
)

PIN_HEAD = "9c15a4f0e2cf8042cb0d4b2f18af31511021d168"
PILOT = Path(__file__).resolve().parents[1]
JSON_SHA = {
    "417": "ed99493d992c71b30e7a4120646af388894032d262b9af5bf299522629fe24ef",
    "941": "2a7d6b191eddf6a92a6bcf74fc818ade8f30836fdd857dc70516f3aa57fa5dde",
}
TEMPLATE_SHA = {
    "417": "c89a01124fb96aa760b6753383eaa79ec6ae07d715d53910754dfe22afff6c8d",
    "941": "76f52e0aa5e25bb094ca1946f5cb820ccbf5e64c1abc54fb4f1f5e45b23eacac",
}
ELECTRON_MOMENTS_SHA = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
RF_CHILD_AND_MESH_SHA = {
    "rf_elastic_multiapp_maxwell_400w_100us_dt1000ns_child.i":
        "655fa43c4c1083e55ea4e845e0e2947c627aec39bc9dd0d384f52468db512698",
    "issue397_maxwell_steady_abs1e11.i":
        "d7d3ea1f2d1fdb3fd63a3e22ca80a750487ef80bcac5af71d11c3c8c2b22a50c",
    "rf_elastic_multiapp_maxwell_400w_100us_dt1000ns_overlay.i":
        "fc5fe6d59ead2f73faa6dacec408798fe595c28f462e2a5915c97f73ee6d0f45",
}
RF_MESH_SHA = "a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e"
RF_PARENT = "rf_elastic_multiapp_parent_400w_100us_dt1000ns_overlay.i"


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def checked_file(file: Path, expected: str, label: str) -> bytes:
    if file.is_symlink() or not file.is_file():
        raise CutoverError("P2_NEWONLY_MISSING_OR_SYMLINK_" + label)
    blob = file.read_bytes()
    if sha(blob) != expected:
        raise CutoverError("P2_NEWONLY_PIN_SHA_MISMATCH_" + label)
    return blob


def prepare_newonly(
    staged_chem_dir: Path, ordered: list[str], variant: str,
    case_manifest: dict, electron_moments_source: Path
) -> dict:
    """Stage the real dual-case New-only contract only in marked Scratch.

    All source/child/table/manifest preflight gates run before any modification.
    Any subsequent runtime/wall/physics owner liveness remains a separate gate.
    """
    if variant not in JSON_SHA or case_manifest.get("case") not in (variant, int(variant)):
        raise CutoverError("P2_NEWONLY_CASE_MISMATCH")
    if case_manifest.get("source_head") != PIN_HEAD:
        raise CutoverError("P2_NEWONLY_SOURCE_HEAD_MISMATCH")
    folder = Path(staged_chem_dir).resolve(strict=True)
    if folder.name != "Issue395_powered_chemistry_ladder" or folder.parent.name != "experiments":
        raise CutoverError("P2_NEWONLY_NOT_EXPECTED_DISPOSABLE_STRUCTURE")
    marker = folder / ".issue633_disposable_scratch"
    if marker.is_symlink() or not marker.is_file() or marker.read_text().strip() != "issue633-scratch-only":
        raise CutoverError("P2_NEWONLY_DISPOSABLE_MARKER_REQUIRED")
    if len(ordered) != 11 or [Path(x).name for x in ordered] != [
        Path(x).name for x in case_manifest.get("ordered_input_paths", [])
    ]:
        raise CutoverError("P2_NEWONLY_PINNED_INPUT_ORDER_MISMATCH")

    staged_inputs = [folder / Path(x).name for x in ordered]
    layer_entries = case_manifest.get("layers", [])
    if len(layer_entries) != 11:
        raise CutoverError("P2_NEWONLY_MISSING_EXACT_MANIFEST")
    for staged, expected in zip(staged_inputs, layer_entries):
        if staged.name != Path(expected["file_path"]).name:
            raise CutoverError("P2_NEWONLY_LAYER_NAME_MISMATCH")
        checked_file(staged, expected["file_sha256"], staged.name)

    js = PILOT / "chemistry" / ("unified_s6_" + variant + "_newonly.json")
    tmpl = PILOT / ("issue633_newonly_s6_" + variant + "_continuity.template.i")
    jsblob = checked_file(js, JSON_SHA[variant], "JSON")
    tmplblob = checked_file(tmpl, TEMPLATE_SHA[variant], "OVERLAY")
    parsed = json.loads(jsblob)
    wanted_eq = {"EI-02", "EI-17", "EI-415", "EI-401", "EI-407", "EI-2069", "H25", "EI-" + variant}
    if set(parsed) != {"species", "equations", "reactions", "ion_surface_current", "drift_diffusion_boundaries"}:
        raise CutoverError("P2_NEWONLY_JSON_SCHEMA_DRIFT")
    if set(parsed["species"]) != {"e", "O2", "O", "O2p", "Om", "Op", "O2a"}:
        raise CutoverError("P2_NEWONLY_SPECIES_DRIFT")
    if set(parsed["equations"]) != wanted_eq or len(parsed["reactions"]) != 8:
        raise CutoverError("P2_NEWONLY_REACTION_BRANCH_DRIFT")
    if parsed["species"]["e"]["transport_coef"] != {
        "type": "lookup",
        "file": "../../Issue91_real_qvt_r3/r3_e0/electron_moments.txt",
        "unit": "reduced", "bounds_policy": "clamp"
    }:
        raise CutoverError("P2_NEWONLY_ELECTRON_TRANSPORT_CONTRACT_DRIFT")
    overlay_txt = tmplblob.decode("utf-8")
    if ("files = 'chemistry/unified_s6_" + variant + "_newonly.json'") not in overlay_txt:
        raise CutoverError("P2_NEWONLY_OVERLAY_JSON_BINDING_MISSING")
    if overlay_txt.count("[Continuity]") != 1 or overlay_txt.count("[Energy]") != 1:
        raise CutoverError("P2_NEWONLY_OVERLAY_OWNERSHIP_DRIFT")

    for name, expected_sha in RF_CHILD_AND_MESH_SHA.items():
        checked_file(folder / name, expected_sha, "MAXWELL_" + name)
    checked_file(folder.parent / "Issue18_qvt_plasma_mapping" / "qvt.msh",
                 RF_MESH_SHA, "MAXWELL_MESH")
    parent_txt = (folder / RF_PARENT).read_text()
    if parent_txt.count("rf_elastic_multiapp_maxwell_400w_100us_dt1000ns_child.i") != 1:
        raise CutoverError("P2_NEWONLY_MAXWELL_PARENT_CHILD_MISMATCH")

    ebytes = checked_file(Path(electron_moments_source), ELECTRON_MOMENTS_SHA, "ELECTRON_MOMENTS")
    if len(ebytes.splitlines()) != 42 or not all(
        len(line.split()) == 3 for line in ebytes.splitlines()
    ):
        raise CutoverError("P2_NEWONLY_ELECTRON_MOMENTS_SHAPE_MISMATCH")
    table_path = folder.parent / "Issue91_real_qvt_r3" / "r3_e0" / "electron_moments.txt"
    if table_path.is_symlink() or (table_path.exists() and sha(table_path.read_bytes()) != ELECTRON_MOMENTS_SHA):
        raise CutoverError("P2_NEWONLY_EXISTING_ELECTRON_MOMENTS_CONFLICT")
    dest_json = folder / "chemistry" / js.name
    if dest_json.is_symlink() or (dest_json.exists() and dest_json.read_bytes() != jsblob):
        raise CutoverError("P2_NEWONLY_EXISTING_CHEMISTRY_CONFLICT")
    resolved_from_json = (dest_json.parent / parsed["species"]["e"]["transport_coef"]["file"]).resolve()
    if resolved_from_json != table_path.resolve():
        raise CutoverError("P2_NEWONLY_RELATIVE_ELECTRON_PATH_MISMATCH")

    # P3-X electron BC/Functor source ownership must be characterized BEFORE
    # P2 starts writing anything. Both P2 and P3 operate only on disposable
    # copies. The existing historical original exact SHA pins are unchanged.
    p3_preflight = inspect_electron_contract(
        {f.name: f.read_bytes() for f in staged_inputs}, ordered, parsed
    )

    # All dependency preflight checks complete; only now edit disposable files.
    previous = {f.name: sha(f.read_bytes()) for f in staged_inputs}
    cutover = retire_in_disposable_scratch(
        folder, ordered, exact_manifest=case_manifest, expected_source_head=PIN_HEAD
    )
    if len(cutover["retired_owners"]) != 26:
        raise CutoverError("P2_NEWONLY_CUTOVER_INCOMPLETE")
    p3_electron = retire_electron_in_disposable_scratch(
        folder, ordered, parsed, p3_preflight, cutover
    )
    if p3_electron["removed_native_electron_owners"] != 10:
        raise CutoverError("P3X_ELECTRON_CUTOVER_INCOMPLETE")

    # P4-X Stage 1: retire ONLY the seven exact duplicate ion producer
    # objects from P3-X's disposable C0. Preserve carrier_one and all
    # non-target Source/Density/Poisson/Lower-D RF/neutral/pressure bytes.
    p4_expected_sha = {
        Path(name).name: (
            p3_electron["C0_after_electron_cutover_sha256"]
            if Path(name).name == P4_C0
            else cutover["files"][Path(name).name]["after_sha256"]
        ) for name in ordered
    }
    p4_owners = retire_p4_duplicate_owners(
        folder, [Path(name).name for name in ordered], parsed,
        post_p3_layer_sha=p4_expected_sha
    )
    if p4_owners["retired_source_materials"] != 6:
        raise CutoverError("P4X_EXACT_SIX_DUPLICATE_MATERIALS_NOT_RETIRED")
    (folder / "migrated_continuity.i").write_bytes(tmplblob)
    dest_json.parent.mkdir(exist_ok=True)
    dest_json.write_bytes(jsblob)
    table_path.parent.mkdir(parents=True, exist_ok=True)
    table_path.write_bytes(ebytes)

    after = {f.name: sha(f.read_bytes()) for f in staged_inputs}
    if sha(dest_json.read_bytes()) != JSON_SHA[variant] or sha(table_path.read_bytes()) != ELECTRON_MOMENTS_SHA:
        raise CutoverError("P2_NEWONLY_STAGE_READBACK_FAILED")
    if (dest_json.parent / parsed["species"]["e"]["transport_coef"]["file"]).resolve() != table_path.resolve():
        raise CutoverError("P2_NEWONLY_TRANSPORT_TARGET_CHANGED")
    if sum(previous[x] != after[x] for x in after) != 6:
        raise CutoverError("P2_NEWONLY_UNEXPECTED_LAYER_DIFF_COUNT")
    if after[P4_C0] != p4_owners["output_c0_sha256"]:
        raise CutoverError("P4X_FINAL_C0_STAGE_SHA_MISMATCH")
    return {
        "status": "P2_NEWONLY_JSON_AND_LAYER11_STAGE_STATIC_PASS_RUNTIME_HOLD",
        "variant": variant, "source_head": PIN_HEAD,
        "retirement": cutover, "p3_x_electron": p3_electron,
        "p4_x_duplicate_producers": p4_owners,
        "P4_X_STAGE1_SOURCE_ONLY": "PASS_7_EXACT_OWNERS_6_REMOVED_1_REPLACED",
        "P4_X_FULL_INTEGRATION": "HOLD_SOURCE_CONSUMER_AND_NATIVE_WAREHOUSE",
        "layers_before_sha256": previous,
        "layers_after_sha256": after, "json_sha256": sha(jsblob),
        "newonly_overlay_sha256": sha(tmplblob),
        "electron_moments_sha256": sha(ebytes), "electron_moments_rows": 42,
        "child_include_sha256": dict(RF_CHILD_AND_MESH_SHA), "mesh_sha256": RF_MESH_SHA,
        "retired_native_ion_owners": 26, "remaining_native_ion_fv_owners": 0,
        "expected_generated_physics_ion_owners": {"FVKernels": 12, "FVBCs": 12},
        "native_p2": "NOT_RUN", "native_p3": "NOT_RUN",
        "native_p4": "NOT_RUN", "D8_NEWONLY_RUNTIME": "HOLD",
        "science": "SCIENCE_HOLD",
    }
