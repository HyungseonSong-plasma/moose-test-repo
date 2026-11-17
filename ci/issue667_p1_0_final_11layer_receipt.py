#!/usr/bin/env python3
"""Issue #667 P1-0: independent immutable S6-417/941 final .i byte receipts.

Static/scratch only. No physics-opt, native P2/P3/P4, private-rate extraction,
repository archive mutation, or scientific parity assertion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PIN = "9c15a4f0e2cf8042cb0d4b2f18af31511021d168"
HIST = "29d1acc6ef7969908b86719e4b95c73a1565136d"
CHEM_REL = Path("experiments/Issue395_powered_chemistry_ladder")
BASE_REL = Path("experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i")
BASE_SHA = "e49e7b63566f16e9eaede7e97ec232338b04a8cdfc019527d73bdb519521abfd"
ARTIFACTS = {
    "417": (13677089020, "441eb637c0eefa947ecbc4e14853ab435e553616b8b6a1e1d11928309409bdcb",
            "b56df6473d3a6e0fefc398f93acacc3afd2a19444135fd2c8d24b2f85b4e1082"),
    "941": (13677375813, "d8643bf2d029a3236876b8912209be61fb85cecadc3125519897e441835d0177",
            "c06ca51b93b18abe2b6de6607cec390a692b224887f3a3b8e623c8b70b9321dd"),
}
SELECTED = {"log_O2p", "log_Om", "log_Op"}
SRC_OBJECTS = {
    "417": {
        "ei415_o2p_source": ("log_O2p", "S_O2p_molar_EI415"),
        "h25_molecular_positive_ion": ("log_O2p", "S_O2p_molar_H25"),
        "ei401_negative_ion_source": ("log_Om", "S_Om_molar_EI401"),
        "legacy8_h05_ei417_op": ("log_Op", "S_Op_molar_EI417"),
        "h25_atomic_positive_ion": ("log_Op", "S_Op_molar_H25"),
    },
    "941": {
        "ei415_o2p_source": ("log_O2p", "S_O2p_molar_EI415"),
        "h25_molecular_positive_ion": ("log_O2p", "S_O2p_molar_H25"),
        "ei401_negative_ion_source": ("log_Om", "S_Om_molar_EI401"),
        "ei941_atomic_positive_ion_source": ("log_Op", "S_Op_molar_EI941"),
        "h25_atomic_positive_ion": ("log_Op", "S_Op_molar_H25"),
    },
}
TAG = re.compile(r"^( *)(?:\[([A-Za-z0-9_./-]*)\])[ \t]*$")
FIELD = re.compile(r"(?m)^    ([A-Za-z0-9_]+)[ \t]*=[ \t]*(.*?)[ \t]*\r?$")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_path(path: Path) -> str:
    return sha(path.read_bytes())


def expected(condition: bool, msg: str) -> None:
    if not condition:
        raise RuntimeError("P1_0_HOLD_" + msg)


def enumerate_blocks(raw: bytes, case: str, ordinal: int, file_name: str) -> list[dict]:
    # No text normalization: offsets and SHA refer to the byte-identical .i file.
    lines = raw.splitlines(keepends=True)
    stack: list[tuple[str, int]] = []
    offset = 0
    records: list[dict] = []
    for line in lines:
        match = TAG.fullmatch(line.decode("utf-8").rstrip("\r\n"))
        if match:
            indent, word = match.groups()
            depth = len(indent) // 2
            expected(len(indent) == 2 * depth, "INVALID_BLOCK_INDENT")
            if word == "":
                expected(len(stack) == depth + 1, "UNBALANCED_BLOCK_CLOSE")
                if len(stack) == 2 and stack[0][0] in ("FVKernels", "FVBCs"):
                    start = stack[-1][1]
                    piece = raw[start:offset + len(line)]
                    f = {m.group(1): m.group(2).strip(" '\"") for m in FIELD.finditer(piece.decode())}
                    if f.get("variable") in SELECTED:
                        records.append({
                            "case": case, "layer_ordinal": ordinal, "file_path": file_name,
                            "section": stack[0][0], "object_name": stack[-1][0],
                            "factory_type": f.get("type"), "variable": f["variable"],
                            "relevant_parameters": f, "block_sha256": sha(piece),
                            "sha_method": "sha256 of exact block bytes inclusive of closing [] newline",
                        })
                stack.pop()
            else:
                expected(len(stack) == depth, "UNBALANCED_BLOCK_OPEN")
                stack.append((word, offset))
        offset += len(line)
    expected(not stack, "UNBALANCED_BLOCK_EOF")
    return records


def run_case(control: Path, output: Path, case: str, archive: Path, option, prep_chem, prep_hybrid, public: dict) -> dict:
    artifact_id, expected_zip, manifest_sha = ARTIFACTS[case]
    expected(hash_path(archive) == expected_zip, case + "_ORIGINAL_ZIP_SHA")
    with zipfile.ZipFile(archive) as z:
        candidates = [n for n in z.namelist() if n.endswith("/case_manifest.json")]
        expected(len(candidates) == 1, case + "_ORIGINAL_MANIFEST_COUNT")
        source_manifest_raw = z.read(candidates[0])
        expected(sha(source_manifest_raw) == manifest_sha, case + "_ORIGINAL_MANIFEST_SHA")
        historic = json.loads(source_manifest_raw)
        expected(historic["source_sha"] == HIST, case + "_ORIGINAL_SOURCE_HEAD")
        raw_paths = historic["input_paths"]
        names = [Path(x).name for x in raw_paths]
        rec = public["cases"][case]
        expected(names == rec["input_order"], case + "_EXACT_ORDER")
        expected(len(names) == len(set(names)) == 10, case + "_TEN_ORIGINAL_FILES")
        original = {}
        for remote in raw_paths:
            name = Path(remote).name
            data = z.read(name)
            expected(sha(data) == historic["input_sha256"][remote], case + "_ORIGINAL_" + name)
            original[name] = data

    # Use the exact original ZIP input bytes for layers 2..10, and only the
    # pinned no-debug D base for layer 1. This is the same D staging contract
    # as the existing CI owner (ci/guards/issue541_arch_s6_native_p2_only.py).
    case_root = output / "scratch" / case
    chemistry = case_root / CHEM_REL
    chemistry.mkdir(parents=True)
    dbase = control / BASE_REL
    expected(hash_path(dbase) == BASE_SHA, case + "_EXACT_DBASE")
    first = names[0]
    (chemistry / first).write_bytes(dbase.read_bytes())
    deck = control / option.p2.DECKS / rec["name"] / "C"
    for name in names[1:]:
        expected(sha(original[name]) == hash_path(deck / name), case + "_ARCHIVE_VS_DECK_" + name)
        (chemistry / name).write_bytes(original[name])
    last = "migrated_continuity.i"
    expected(hash_path(deck / last) == rec["files_sha256"]["C"][last],
             case + "_MIGRATED_SOURCE_SHA")
    shutil.copyfile(deck / last, chemistry / last)
    order = names + [last]
    ordered = [str(CHEM_REL / name) for name in order]
    expected(len(ordered) == 11, case + "_STAGING_ORDER")

    migrate = option.canonicalize_staged_D_inputs(chemistry, ordered)
    typemap = option.remap_staged_fem_types(chemistry, ordered)
    chem = prep_chem(chemistry, ordered, case)
    hybrid = prep_hybrid(chemistry, ordered, case, chemistry_cutover=chem)
    expected(hash_path(chemistry / last) == hybrid["overlay_sha256"],
             case + "_FINAL_OVERLAY_SHA")
    expected(hybrid["removed_generated_owner_count"] == 10, case + "_HYBRID_REMOVALS")
    expected(hybrid["rebound_native_sheath_bc_count"] == 8, case + "_SHEATH_COUNT")
    expected(hybrid["integrated_reaction_count"] == 8, case + "_REACTION_COUNT")

    # Preserve exactly the 11 .i files. No rate lookup files, original ZIP,
    # Python source, or other runtime/generated directory enters the Artifact.
    export = output / "cases" / case / "final_11_inputs"
    export.mkdir(parents=True)
    layers: list[dict] = []
    blocks: list[dict] = []
    for ordinal, name in enumerate(order, 1):
        data = (chemistry / name).read_bytes()
        (export / name).write_bytes(data)
        layer = {
            "case": case, "layer_ordinal": ordinal, "file_path": str(CHEM_REL / name),
            "source_head": PIN, "file_sha256": sha(data), "file_size": len(data),
            "archived_origin_sha256": sha(original[name]) if ordinal > 1 and ordinal <= 10 else None,
            "actual_file_bytes_preserved": True, "status": "PASS",
        }
        layers.append(layer)
        blocks.extend(enumerate_blocks(data, case, ordinal, str(CHEM_REL / name)))
    selected = [b for b in blocks if b["section"] == "FVKernels"]
    bcs = [b for b in blocks if b["section"] == "FVBCs"]
    expected(len(selected) == 14, case + "_EXPECTED_14_ION_FV_KERNELS")
    expected(len(bcs) == 12, case + "_EXPECTED_12_ION_FV_BCS")
    sources = [b for b in selected if b["object_name"] in SRC_OBJECTS[case]]
    expected(len(sources) == 5, case + "_EXPECTED_FIVE_SOURCES")
    expected(len({(b["section"], b["object_name"]) for b in blocks}) == 26,
             case + "_DUPLICATE_NATIVE_OWNER")
    for name, (variable, functor) in SRC_OBJECTS[case].items():
        hits = [b for b in sources if b["object_name"] == name]
        expected(len(hits) == 1, case + "_SOURCE_MISSING_OR_DUPLICATE_" + name)
        b = hits[0]
        p = b["relevant_parameters"]
        expected(b["factory_type"] == "FVCoupledForce" and b["variable"] == variable
                 and p.get("v") == functor and p.get("coef") == "1.0"
                 and p.get("block") == "plasma",
                 case + "_SOURCE_BINDING_" + name)
    b1 = next(x for x in sources if x["object_name"] == "ei415_o2p_source")
    b2 = next(x for x in sources if x["object_name"] == "h25_molecular_positive_ion")
    expected(b1["layer_ordinal"] == 5 and b2["layer_ordinal"] == 10
             and b1["block_sha256"] != b2["block_sha256"],
             case + "_B1_B2_DISTINCT")
    recout = {
        "case": case, "source_head": PIN, "historical_head": HIST,
        "historical_artifact_id": artifact_id, "historical_zip_sha256": expected_zip,
        "historical_case_manifest_sha256": manifest_sha, "ordered_input_paths": ordered,
        "layer_count": len(layers), "layers": layers, "ion_native_blocks": blocks,
        "verified_ion_fv_kernel_count": len(selected), "verified_ion_fv_bc_count": len(bcs),
        "verified_source_count": len(sources),
        "b2_source_block_sha256": b2["block_sha256"],
        "b1_source_block_sha256": b1["block_sha256"],
        "stage_reconstruction": {
            "canonicalization": migrate["status"], "type_remap": typemap["status"],
            "chemistry_overlay_sha256": chem["overlay_sha256"],
            "final_hybrid_overlay_sha256": hybrid["overlay_sha256"],
        },
        "status": "FINAL_11_BYTES_PRESERVED_AND_26_OBJECTS_VALIDATED",
        "P2": "NOT_RUN", "P3": "NOT_RUN", "P4": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }
    (output / "cases" / case / "case_manifest.json").write_text(
        json.dumps(recout, indent=2, sort_keys=True) + "\n")
    return recout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", type=Path, required=True)
    ap.add_argument("--archive-417", type=Path, required=True)
    ap.add_argument("--archive-941", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    control = args.control.resolve()
    output = args.output.resolve()
    expected(not output.exists(), "REFUSE_OVERWRITE")
    output.mkdir(parents=True, mode=0o700)
    expected(subprocess.check_output(
        ["git", "-C", str(control), "rev-parse", "HEAD"], text=True).strip() == PIN,
        "CONTROL_HEAD_PIN")
    sys.path.insert(0, str(control / "experiments/Issue402_plasma_dsl_g1"))
    import public_option_s6_p2 as option
    from chemistry.prepare_s6_run_input import prepare as prep_chem
    from chemistry.prepare_hybrid_json_s6 import prepare as prep_hybrid

    option.p2.preflight(control)
    public = json.loads((control / option.p2.DECKS / "manifest.json").read_text())
    all_cases = {}
    for case, archive in (("417", args.archive_417), ("941", args.archive_941)):
        all_cases[case] = run_case(
            control, output, case, archive.resolve(), option, prep_chem, prep_hybrid, public
        )
        print("P1_0_CASE_FINAL_BYTES_PASS", case,
              all_cases[case]["b2_source_block_sha256"], flush=True)
    common = {
        "schema": "issue667_p1_0_exact_s6_final_11layer_source_manifest_v1",
        "source_head": PIN, "historical_head": HIST,
        "input_case_names": ["417", "941"],
        "cases": {
            case: {
                "layer_count": v["layer_count"], "layers": v["layers"],
                "ion_native_blocks": v["ion_native_blocks"], "ordered_input_paths": v["ordered_input_paths"],
                "historical_zip_sha256": v["historical_zip_sha256"],
                "historical_artifact_id": v["historical_artifact_id"],
            }
            for case, v in all_cases.items()
        },
        "gates": {
            "actual_final_input_bytes": "PRESERVED_11_PER_CASE",
            "independent_file_and_block_sha": "PASS",
            "original_historical_zip_sha": "PASS_BOTH",
            "native_ion_26_object_inventory": "PASS_BOTH",
            "P1_B2_417": "PASS_EXACT_FILE_AND_BLOCK_SHA",
            "P1_E_INTEGRATION": "NOT_RUN",
            "P2": "NOT_RUN", "P3": "NOT_RUN", "P4": "NOT_RUN",
            "science": "SCIENCE_HOLD",
        },
        "privacy": "NO_PRIVATE_RATE_BYTES_INCLUDED",
    }
    (output / "common_manifest.json").write_text(
        json.dumps(common, indent=2, sort_keys=True) + "\n")
    (output / "status.json").write_text(
        json.dumps({"status": "PASS", "source_head": PIN, "cases": ["417", "941"],
                    "common_manifest_sha256": hash_path(output / "common_manifest.json"),
                    "P2": "NOT_RUN", "P3": "NOT_RUN", "P4": "NOT_RUN",
                    "science": "SCIENCE_HOLD"}, indent=2, sort_keys=True) + "\n")
    # All staged inputs are duplicated in cases/.../final_11_inputs; remove the
    # larger scratch tree before artifact upload and preserve only final bytes.
    shutil.rmtree(output / "scratch")
    print("P1_0_FINAL_11LAYER_MANIFEST_PASS", PIN,
          hash_path(output / "common_manifest.json"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
