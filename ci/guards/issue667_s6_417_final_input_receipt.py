#!/usr/bin/env python3
"""Issue #667 P1-0: preserve exact-head S6-417 hybrid-D input bytes.

No Native executable, solve, historical rewrite, or private-rate source.
This is the CI-only evidence producer, not a science acceptance tool.
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
from collections import Counter
from pathlib import Path

PINNED_PR_HEAD = "9c15a4f0e2cf8042cb0d4b2f18af31511021d168"
HISTORICAL_HEAD = "29d1acc6ef7969908b86719e4b95c73a1565136d"
ZIP_SHA256 = "441eb637c0eefa947ecbc4e14853ab435e553616b8b6a1e1d11928309409bdcb"
CASE = "S6-417-407-2069-H25"
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
EXPECTED_SOURCE = {
    "ei415_o2p_source": ("log_O2p", "S_O2p_molar_EI415"),
    "h25_molecular_positive_ion": ("log_O2p", "S_O2p_molar_H25"),
    "ei401_negative_ion_source": ("log_Om", "S_Om_molar_EI401"),
    "legacy8_h05_ei417_op": ("log_Op", "S_Op_molar_EI417"),
    "h25_atomic_positive_ion": ("log_Op", "S_Op_molar_H25"),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def stage_archived_inputs(archive: Path, scratch: Path, control: Path):
    if file_sha(archive) != ZIP_SHA256:
        raise ValueError("ORIGINAL_ARCHIVE_ZIP_SHA_MISMATCH")
    chemistry = scratch / CHEM
    chemistry.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        originals = [x for x in z.namelist() if x.endswith(".i")]
        manifests = [x for x in z.namelist() if x.endswith("/case_manifest.json")]
        if len(manifests) != 1 or len(originals) != 10:
            raise ValueError("ORIGINAL_ARCHIVE_LAYOUT_CHANGED")
        manifest = json.loads(z.read(manifests[0]))
        order = manifest["input_paths"]
        if (manifest.get("case") != CASE or
                manifest.get("source_sha") != HISTORICAL_HEAD or len(order) != 10):
            raise ValueError("ORIGINAL_ARCHIVE_CASE_SOURCE_OR_ORDER_CHANGED")
        archived = {}
        entries = {}
        for index, path in enumerate(order, 1):
            name = Path(path).name
            if not name.endswith(".i") or ".." in Path(path).parts:
                raise ValueError("UNSAFE_ARCHIVED_INPUT")
            entry = [x for x in originals if Path(x).name == name]
            if len(entry) != 1 or name in archived:
                raise ValueError("ARCHIVED_INPUT_MISSING_OR_DUPLICATE")
            data = z.read(entry[0])
            original_sha = digest(data)
            if manifest["input_sha256"][path] != original_sha:
                raise ValueError("ARCHIVED_LAYER_SHA_DIFF:" + name)
            if re.search(rb"(?mi)^\s*!include\b", data):
                raise ValueError("MOOSERAW_INCLUDE_REQUIRES_CLOSURE:" + name)
            archived[name] = data
            entries[name] = {
                "layer_ordinal": index, "source_manifest_path": path,
                "archived_sha256": original_sha, "archived_bytes": len(data),
                "final_sha256": None,
            }
        if len(archived) != 10:
            raise ValueError("ARCHIVED_INPUT_COUNT_NOT_TEN")
    base = control / "experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i"
    if not base.is_file() or not base.stat().st_size:
        raise ValueError("PR665_D_BASE_MISSING")
    for index, path in enumerate(order):
        name = Path(path).name
        (chemistry / name).write_bytes(base.read_bytes() if index == 0 else archived[name])
    (chemistry / "migrated_continuity.i").write_text(
        "# Scratch C placeholder replaced by exact-head Chemistry/Hybrid source.\n",
        encoding="utf-8",
    )
    # The HybD preparer reads the existing PUBLIC electron-moments table.
    public_table = (control / "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt")
    if not public_table.is_file():
        raise ValueError("PUBLIC_ELECTRON_MOMENTS_SOURCE_MISSING")
    destination = scratch / "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
    destination.parent.mkdir(parents=True)
    shutil.copyfile(public_table, destination)
    return chemistry, [str(CHEM / Path(x).name) for x in order] + [
        str(CHEM / "migrated_continuity.i")
    ], entries, manifest


def produce(control: Path, archive: Path, output: Path):
    root_head = subprocess.check_output(
        ["git", "-C", str(control), "rev-parse", "HEAD"], text=True
    ).strip()
    if root_head != PINNED_PR_HEAD:
        raise ValueError("PR665_SOURCE_HEAD_CHANGED:" + root_head)
    if output.exists():
        raise ValueError("REFUSE_OVERWRITING_EVIDENCE")
    output.mkdir(parents=True)
    stage = output / "scratch"
    stage.mkdir()
    chemistry, ordered, original, src_manifest = stage_archived_inputs(
        archive, stage, control
    )
    sys.path.insert(
        0, str(control / "experiments/Issue402_plasma_dsl_g1")
    )
    import public_option_s6_p2 as option
    from chemistry.prepare_s6_run_input import prepare as prepare_chemistry
    from chemistry.prepare_hybrid_json_s6 import prepare as prepare_hybrid
    from chemistry.retire_s6_ion_fv_owners import cutover_texts

    canonical = option.canonicalize_staged_D_inputs(chemistry, ordered)
    factories = option.remap_staged_fem_types(chemistry, ordered)
    chem_receipt = prepare_chemistry(chemistry, ordered, "417")
    hybrid_receipt = prepare_hybrid(
        chemistry, ordered, "417", chemistry_cutover=chem_receipt
    )
    if len(ordered) != 11:
        raise ValueError("FINAL_11_LAYER_COUNT_INVALID")
    final = {}
    for item in ordered:
        name = Path(item).name
        data = (chemistry / name).read_bytes()
        if not data or re.search(rb"(?mi)^\s*!include\b", data):
            raise ValueError("EMPTY_OR_UNRESOLVED_INCLUDE:" + name)
        final[name] = data.decode("utf-8")
    if (chemistry / "private_rates").exists():
        raise ValueError("PRIVATE_RATES_MUST_NOT_EXIST_IN_STAGE")
    _, cutover = cutover_texts(final)
    if (cutover["old_native_fv_kernels"] != 14 or
            cutover["old_native_fv_bcs"] != 12 or
            len(cutover["retired_owners"]) != 26):
        raise ValueError("FINAL_26_NATIVE_OWNERS_MISMATCH")
    ion_owners = {x["name"]: x for x in cutover["retired_owners"]}
    for name, (variable, producer) in EXPECTED_SOURCE.items():
        row = ion_owners.get(name)
        if not row or row["section"] != "FVKernels" or row["type"] != "FVCoupledForce" or row["variable"] != variable:
            raise ValueError("FINAL_SOURCE_OWNER_MISSING:" + name)
        text = final[row["file"]]
        pattern = re.compile(
            r"(?m)^  \[" + re.escape(name) + r"\]\r?\n"
            r"(?P<body>(?:^    [^\r\n]*\r?\n)+)"
            r"^  \[\](?:\r?\n|$)"
        )
        matches = [
            m for m in pattern.finditer(text)
            if re.findall(r"(?m)^\[([A-Za-z0-9_]+)\]\s*$", text[:m.start()])[-1:] == ["FVKernels"]
        ]
        if len(matches) != 1 or not re.search(
            r"(?m)^    v\s*=\s*" + re.escape(producer) + r"\s*$",
            matches[0].group("body"),
        ):
            raise ValueError("FINAL_SOURCE_PRODUCER_EDGE_INVALID:" + name)

    # Copy only the finalized 11 .i bytes into the public CI artifact.
    deliverable = output / "artifact"
    preserved = deliverable / "final_inputs"
    preserved.mkdir(parents=True)
    layers = []
    for index, item in enumerate(ordered, 1):
        name = Path(item).name
        src = (chemistry / name)
        dst = preserved / name
        shutil.copyfile(src, dst)
        expected = file_sha(src)
        if file_sha(dst) != expected:
            raise ValueError("PRESERVED_FILE_READBACK_MISMATCH:" + name)
        row = original.get(name, {
            "layer_ordinal": index,
            "source_manifest_path": None,
            "archived_sha256": None,
            "archived_bytes": None,
        })
        layers.append({
            **row,
            "layer_ordinal": index,
            "file_name": name, "final_sha256": expected,
            "final_bytes": dst.stat().st_size,
            "final_bytes_readback_verified": True,
        })
    # The integrated JSON contains mechanism descriptors, not rate lookup data.
    public_json = chemistry / hybrid_receipt["integrated_mechanism_json"]
    shutil.copyfile(public_json, deliverable / public_json.name)

    report = {
        "schema": "issue667.p1_0.s6_417.final_11_layer_ci.v1",
        "status": "FINAL_11_LAYER_PRESERVED_SOURCE_BOUND_NO_NATIVE_RUN",
        "case": CASE, "source_pr": 665, "source_head": root_head,
        "historical_source": HISTORICAL_HEAD,
        "original_artifact_id": 13677089020,
        "original_zip_sha256": ZIP_SHA256,
        "original_case_manifest_sha256": digest(
            json.dumps(src_manifest, sort_keys=True).encode("utf-8")
        ),
        "first_layer_override": "experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i",
        "first_layer_override_sha256": file_sha(
            control / "experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i"
        ),
        "preparation": {
            "canonicalized": canonical["status"],
            "factories": factories["status"],
            "chemistry": chem_receipt["status"],
            "hybrid": hybrid_receipt["status"],
            "sidecar_sha256": hybrid_receipt["overlay_sha256"],
        },
        "ordered_files": layers,
        "ion_owners": cutover["retired_owners"],
        "native_ion_counts": {"FVKernels": 14, "FVBCs": 12, "sources": 5},
        "sciences": {"native_P2": "NOT_RUN", "native_P3": "NOT_RUN", "native_P4": "NOT_RUN", "science": "SCIENCE_HOLD"},
        "private_rate_file_bytes_in_artifact": False,
        "reproduction": "Archived verified layers 2-10 plus exact PR665 D-base layer 1, existing D canonicalize/FEM-remap/Chemistry/Hybrid helpers, generated Hybrid sidecar",
        "limits": "No runtime Native --check-input or solver; artifact source SHA is PR665 pinned code. Artifact records exact direct staged .i bytes only.",
    }
    (deliverable / "manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("P1_0_S6_417_PRESERVED_11_SHA_PASS_26_BLOCK_SHA_PASS", flush=True)
    print("SOURCE_PR665_HEAD=" + root_head, flush=True)
    print("ARTIFACT_MANIFEST_SHA256=" + file_sha(deliverable / "manifest.json"), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        produce(args.control.resolve(), args.archive.resolve(), args.output.resolve())
    except Exception as exc:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        safe = {
            "status": "HOLD",
            "blocker": type(exc).__name__ + ":" + str(exc)[:300],
            "source_head_expected": PINNED_PR_HEAD,
            "P2": "NOT_RUN", "P3": "NOT_RUN", "P4": "NOT_RUN",
            "science": "SCIENCE_HOLD",
        }
        (output / "failure_receipt.json").write_text(
            json.dumps(safe, indent=2) + "\n", encoding="utf-8"
        )
        print("P1_0_S6_417_HOLD " + safe["blocker"], file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
