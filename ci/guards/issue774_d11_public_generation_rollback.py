#!/usr/bin/env python3
"""#774 D11 public-only non-Native generated input replay and B rollback custody.

Execute the existing Public D 100-row Physics generator against independently
copied, pinned disposable S6 417/941 P4-X staged inputs. Do not stage private
rates, alter the original scratch, create a new Legacy Physics Factory, or
claim Native P2/P3/P4 or global consumer zero. Source rollback = original
verified New-only B source tree and archived W1 ELF, not in-place main revert.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

REPO_HEAD = re.compile(r"[0-9a-f]{40}\Z")
BASE_B = "c77d2f773eee96c30eeca49d7486fea22ea8e557"
W1_RUN = "45177755891"
B_ELF_SHA = "d6a87b61f7e3e8d06767f7a245c51e846293af740653609492d2e3f9714ac62c"
B_ARCHIVE_SHA = "37104cdcae3d7009445258302b1008e0af416e2301d78d4b21c47246bbe2ba43"
OCI = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
THERMAL = "PhysicsFVThermalDiffusion"
TARGET = re.compile(r"\b" + THERMAL + r"\b")
MOoSE_TYPE = re.compile(r"(?m)^\s*type\s*=\s*([A-Za-z_]\w*)\s*$")
CASES = ("417", "941")
ELF_MEMBER = "physics-opt"
MEMBERS = {
    "physics-opt",
    "lib/libphysics-opt.so.0",
    "lib/libphysics_test-opt.so.0",
}


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError("ISSUE774_D11_" + code)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, timeout=45, check=False)
    need(p.returncode == 0, "GIT_SOURCE_UNAVAILABLE")
    return p.stdout.strip()


def validate_factory_outputs(layers: dict[str, bytes], mechanism: dict) -> dict:
    """Type tokens from *actual written output*, not scanner source strings."""
    need(len(layers) == 11 and all(name.endswith(".i") for name in layers),
         "GENERATED_LAYER_COUNT_OR_PATH")
    matches = []
    type_counts = {}
    for name, contents in sorted(layers.items()):
        need(isinstance(contents, bytes), "OUTPUT_NOT_BYTES")
        text = contents.decode("utf-8", "strict")
        need(TARGET.search(text) is None,
             "GENERATED_LEGACY_FACTORY:" + name)
        types = MOoSE_TYPE.findall(text)
        type_counts[name] = len(types)
        matches.extend(types)
    need(isinstance(mechanism, dict), "BAD_GENERATED_MECHANISM")
    json_bytes = json.dumps(mechanism, sort_keys=True).encode()
    need(TARGET.search(json_bytes.decode()) is None,
         "GENERATED_LEGACY_FACTORY_IN_JSON")
    generated_type_fields = []
    def collect(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "type" and isinstance(value, str):
                    generated_type_fields.append(value)
                collect(value)
        elif isinstance(obj, list):
            for value in obj:
                collect(value)
    collect(mechanism)
    need(THERMAL not in matches and THERMAL not in generated_type_fields,
         "GENERATED_FACTORY_FIELD_REINTRODUCED")
    return {
        "total_input_type_statements": len(matches),
        "input_type_statements_by_layer": type_counts,
        "actual_input_unique_types": sorted(set(matches)),
        "actual_mechanism_type_fields": sorted(set(generated_type_fields)),
        "old_thermal_factory_refs": 0,
        "output_layer_sha256": {n: sha(v) for n, v in sorted(layers.items())},
        "mechanism_sha256": sha(json_bytes),
    }


def verify_rollback(root: Path, baseline: Path, w1: Path, native: Path,
                    *, expected_head: str) -> dict:
    """Rollback *readiness* custody, not a switch of main or old-type support."""
    current = git(root, "rev-parse", "HEAD")
    b_head = git(baseline, "rev-parse", "HEAD")
    need(current == expected_head and REPO_HEAD.fullmatch(current) is not None,
         "CURRENT_HEAD_MISMATCH")
    need(b_head == BASE_B, "ROLLBACK_BASE_SHA_MISMATCH")
    current_physics = git(root, "rev-parse", "HEAD:physics_app")
    b_physics = git(baseline, "rev-parse", "HEAD:physics_app")
    need(current_physics == b_physics,
         "ROLLBACK_PHYSICS_APP_TREE_DRIFT")
    need(not (root / "physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C").exists()
         and not (baseline / "physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C").exists(),
         "ROLLBACK_REINTRODUCES_RETIRED_FACTORY")
    manifest = json.loads((w1 / "identity.json").read_text())
    expected = {"source_head": BASE_B, "run_id": W1_RUN,
                "binary_sha256": B_ELF_SHA, "oci": OCI,
                "build_count": 1, "archive_member_count": 3,
                "archive_roundtrip_check": "PASS", "private_data_bundled": False}
    need(all(manifest.get(key) == value for key, value in expected.items()),
         "ROLLBACK_W1_PROVENANCE_MISMATCH")
    raw = (w1 / "physics-opt-and-app-libs.tar.gz").read_bytes()
    need(sha(raw) == B_ARCHIVE_SHA == manifest.get("archive_sha256"),
         "ROLLBACK_W1_ARCHIVE_SHA_MISMATCH")
    entries = manifest.get("file_records", [])
    need(isinstance(entries, list) and {x["stored_path"] for x in entries} == MEMBERS,
         "ROLLBACK_W1_APP_LIB_SET_MISMATCH")
    records = {x["stored_path"]: x for x in entries}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        need(set(archive.getnames()) == MEMBERS,
             "ROLLBACK_W1_TAR_MEMBER_SET_MISMATCH")
        for member in sorted(MEMBERS):
            stored = archive.getmember(member)
            need(stored.isfile() and stored.size == records[member]["bytes"],
                 "ROLLBACK_W1_MEMBER_SIZE_MISMATCH:" + member)
            f = archive.extractfile(stored)
            need(f is not None, "ROLLBACK_W1_MEMBER_MISSING:" + member)
            blob = f.read()
            need(sha(blob) == records[member]["sha256"],
                 "ROLLBACK_W1_MEMBER_SHA_MISMATCH:" + member)
            if member == ELF_MEMBER:
                need(blob.startswith(b"\x7fELF") and sha(blob) == B_ELF_SHA,
                     "ROLLBACK_W1_ELF_SHA_MISMATCH")
    receipt = json.loads((native / "p05-out/p05_negative_receipt.json").read_text())
    need(receipt.get("source_head") == BASE_B and
         receipt.get("binary_sha256") == B_ELF_SHA and
         receipt.get("status") == "PASS_16_INTENDED_NATIVE_REJECTIONS" and
         receipt.get("native_tests_completed") == 16 and
         receipt.get("native_expected_rejections") == 16 and
         receipt.get("private_data_in_artifacts") is False and
         receipt.get("tmpfs_cleanup_verified") is True and
         set(receipt.get("cases", {})) == set(CASES),
         "ROLLBACK_NATIVE_EVIDENCE_MISMATCH")
    for case in CASES:
        part = receipt["cases"][case]
        need(part.get("clean_syntax_ok") is True and part.get("clean_exit") == 0
             and len(part.get("source_layer_sha256", {})) == 11,
             "ROLLBACK_NATIVE_P05_CASE_MISMATCH:" + case)
    return {
        "status": "B_SOURCE_AND_W1_NATIVE_CUSTODY_VERIFIED",
        "B_sha": BASE_B, "current_sha": current,
        "identical_physics_app_git_tree": current_physics,
        "B_physics_app_git_tree": b_physics,
        "B_W1_run_id": W1_RUN, "B_W1_elf_sha256": B_ELF_SHA,
        "B_W1_archive_sha256": B_ARCHIVE_SHA,
        "B_native_P05_status": receipt["status"],
        "B_native_expected_negative_controls": 16,
        "rollback_executed": False,
        "old_thermal_input_support_restored": False,
        "merged_code_rollback_authorized": False,
    }


def replay_generated_public_d(root: Path, stage: Path, scratch: Path) -> dict:
    chem_root = root / "experiments/Issue402_plasma_dsl_g1/chemistry"
    sys.path.insert(0, str(chem_root))
    from prepare_public_d_newphysics_100row import (  # noqa: E402
        ORIGINAL_TABLE, ORIGINAL_TABLE_SHA256, stage_public_d_physics,
        check_100row_table,
    )
    need(ORIGINAL_TABLE.exists() and
         sha(check_100row_table(ORIGINAL_TABLE)) == ORIGINAL_TABLE_SHA256,
         "ORIGINAL_PUBLIC_100ROW_TABLE_DRIFT")
    readiness = json.loads((stage / "readiness.json").read_text())
    stages = readiness.get("stage_cases")
    need(isinstance(stages, dict) and set(CASES) <= set(stages),
         "PINNED_STAGER_CASES_MISSING")
    result = {}
    for case in CASES:
        source = stage / "scratch" / case / "experiments" / "Issue395_powered_chemistry_ladder"
        need(source.is_dir() and not source.is_symlink(), "STAGED_CASE_NOT_DIRECTORY:" + case)
        names = [Path(p).name for p in stages[case]["ordered"]]
        need(len(names) == 11 and len(set(names)) == 11 and
             all(n.endswith(".i") for n in names),
             "STAGER_ORDERED_LAYER_COUNT:" + case)
        original = {n: sha((source / n).read_bytes()) for n in names}
        original_table = (source.parent / "Issue91_real_qvt_r3/r3_e0/electron_moments.txt")
        need(original_table.is_file() and not original_table.is_symlink(),
             "STAGED_42ROW_TABLE_MISSING:" + case)
        target = scratch / case / "experiments" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, symlinks=True)
        copied_table = target.parent / "Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
        copied_table.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original_table, copied_table)
        record = stage_public_d_physics(target, case, names,
                                        original_table=ORIGINAL_TABLE)
        need(record.get("case") == case and record.get("disposable_only") is True
             and record.get("original_table_rows") == 100
             and record.get("expected_physics_ion_kernel_count") == 12
             and record.get("expected_physics_ion_bc_count") == 12
             and record.get("expected_electron_sheath_bc_count") == 8
             and record.get("chemistry_reaction_count") == 8
             and all(record.get(key) == "NOT_RUN"
                     for key in ("P2", "P3", "P4")),
             "PUBLIC_D_GENERATOR_RECEIPT_CONTRACT:" + case)
        changed = (target / "chemistry" /
                   ("public_d_s6_" + case + "_physics.json"))
        need(changed.is_file() and not changed.is_symlink(),
             "PUBLIC_D_GENERATED_MECHANISM_MISSING:" + case)
        rendered = {name: (target / name).read_bytes() for name in names}
        observed = validate_factory_outputs(rendered, json.loads(changed.read_text()))
        need(record.get("staged_11layer_sha256") == observed["output_layer_sha256"],
             "PUBLIC_D_RECORDED_LAYER_SHA_MISMATCH:" + case)
        need(all(sha((source / name).read_bytes()) == original[name] for name in names),
             "PUBLIC_D_MUTATED_ORIGINAL_STAGING:" + case)
        need(sha(ORIGINAL_TABLE.read_bytes()) == ORIGINAL_TABLE_SHA256,
             "PUBLIC_D_MODIFIED_ORIGINAL_100ROW")
        need(b"PhysicsFVThermalDiffusion" not in copied_table.read_bytes(),
             "PUBLIC_D_RETIRED_TOKEN_IN_COPIED_TABLE")
        result[case] = {
            "generator": "stage_public_d_physics",
            "generator_status": "PASS_PUBLIC_INPUT_GENERATION_NO_NATIVE",
            "generated_json_name": record["json_name"],
            "generated_overlay_sha256": record["overlay_sha256"],
            "source_11_layer_sha256": original,
            "output": observed,
            "original_100row_table_sha256": ORIGINAL_TABLE_SHA256,
            "source_staging_unchanged": True,
            "protected_rates_accessed": False,
        }
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expected-head", required=True)
    p.add_argument("--repo-root", type=Path, required=True)
    p.add_argument("--baseline-b", type=Path, required=True)
    p.add_argument("--w1-artifact", type=Path, required=True)
    p.add_argument("--native-artifact", type=Path, required=True)
    p.add_argument("--staged", type=Path, required=True)
    p.add_argument("--scratch", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    args = p.parse_args()
    out = {
        "schema": "issue774.d11.public_d_generator_and_B_rollback.v0.1",
        "source_head": args.expected_head, "public_d_cases": {},
        "B_rollback": {}, "status": "HOLD",
        "old_input_support": "EXPLICITLY_NOT_REQUIRED",
        "protected_rates_accessed": False,
        "all_generated_or_external_consumers_closed": False,
        "native_new_run": False, "science": "SCIENCE_HOLD",
        "main_merge": False, "safe_to_delete": False,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    try:
        out["B_rollback"] = verify_rollback(
            args.repo_root, args.baseline_b, args.w1_artifact,
            args.native_artifact, expected_head=args.expected_head)
        out["public_d_cases"] = replay_generated_public_d(
            args.repo_root, args.staged, args.scratch)
        need(set(out["public_d_cases"]) == set(CASES),
             "TWO_PUBLIC_D_CASES_NOT_RUN")
        out["status"] = "PASS_TWO_GENERATED_PUBLIC_D_AND_B_ROLLBACK_CUSTODY"
    except (ValueError, OSError, KeyError, TypeError, UnicodeError,
            json.JSONDecodeError, tarfile.TarError) as err:
        out["status"] = "HOLD_GENERATION_OR_ROLLBACK_PROVENANCE"
        out["error_type"] = type(err).__name__
        out["error_code"] = str(err)[:250] if str(err).startswith("ISSUE774_D11_") else "UNEXPECTED"
    args.receipt.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("D11_PUBLIC_GENERATION_AND_ROLLBACK=" + out["status"])
    return 0 if out["status"] == "PASS_TWO_GENERATED_PUBLIC_D_AND_B_ROLLBACK_CUSTODY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
