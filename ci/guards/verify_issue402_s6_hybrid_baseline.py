#!/usr/bin/env python3
"""Read-only SHA-pinned Issue402 S6-417/941 P3 and P4 diagnostic receipt.

This verifies operational source/byte evidence, not scientific parity.
No Native solver execution, artifact upload, or active model modification.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
import re
import shutil
import sys
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "ci/baselines/issue402_s6_hybrid_20261114.json"
EXISTING = ROOT / "experiments/Issue402_plasma_dsl_g1/verify_chemistry_p3_evidence.py"
ZIP_SHA = {
    "417": "563800ba985c3966d24aa0196fbe8ce46c9e1f5f1a1936685c6b5ff76c77a195",
    "941": "87150a4b7db1647aa6a46731335ea1efa28a2998558cedd83df08d707c210d7e",
}

class ReferenceError(ValueError):
    pass

def require(condition, error):
    if not condition:
        raise ReferenceError(error)

def digest(stream):
    h = hashlib.sha256()
    while True:
        data = stream.read(1024 * 1024)
        if not data:
            break
        h.update(data)
    return h.hexdigest()

def file_sha(path):
    with path.open("rb") as f:
        return digest(f)

def member_sha(z, name):
    with z.open(name) as f:
        return digest(f)

def check_retention(b):
    """Independently read-back original ZIP bytes != maintained P3/P4 replay."""
    ret = b.get("retention", {})
    require(ret.get("durable_backup") ==
            "INDEPENDENT_BACKUP_READBACK_VERIFIED", "BACKUP_READBACK_STATUS")
    require(ret.get("cannot_retire_unique_p3_p4_replay_until_preserved") is True,
            "LEGACY_REPLAY_PROTECTION")
    independent = ret.get("independent_copy", {})
    require(independent.get("provider") == "Google Drive" and
            independent.get("visibility") == "OWNER_ONLY_NON_SHARED" and
            independent.get("readback_verified_date") == "2026-11-15" and
            independent.get("folder_url") ==
                "https://drive.google.com/drive/folders/1KbxP1TjW1u-9cRttyLelo3M2hXjrAAKb" and
            independent.get("source_record") ==
                "docs/development/2026-11-15_issue541_arch_s6_retention_readback.md" and
            independent.get("maintenance_free_worm_archive") == "NOT_PROVEN",
            "BACKUP_PROVENANCE_NOT_VERIFIED")
    replay = ret.get("replay_contract", {})
    require(replay.get("unique_100us_two_case_p3_p4") == "KEEP_HOLD" and
            replay.get("maintained_independent_replacement") == "NOT_PROVEN" and
            replay.get("science") == "SCIENCE_HOLD",
            "UNIQUE_P3_P4_REPLAY_UNPROVEN")
    cases = b.get("cases", {})
    require(set(cases) == {"417", "941"}, "ARCHIVE_CASE_SET")
    for case, expected in {
        "417": {
            "url": "https://drive.google.com/file/d/1jDJIgLRyuk-Gpy2AhBYJmN3t2OjWdnZX/view",
            "sha": ZIP_SHA["417"], "bytes": 98686127,
        },
        "941": {
            "url": "https://drive.google.com/file/d/1E7xzCeMqIUhBFHov1WsvDKBPkEB1PURf/view",
            "sha": ZIP_SHA["941"], "bytes": 98635164,
        },
    }.items():
        c = cases[case]
        stored = c.get("independent_copy", {})
        require(c.get("archive_sha256") == expected["sha"] and
                c.get("archive_bytes") == expected["bytes"] and
                stored.get("url") == expected["url"] and
                stored.get("readback_sha256") == expected["sha"] and
                stored.get("readback_bytes") == expected["bytes"],
                "BACKUP_CASE_READBACK_MISMATCH:" + case)


def load_receipt():
    b = json.loads(RECEIPT.read_text(encoding="utf-8"))
    require(b.get("schema") == "issue402.s6.hybrid.reference_receipt.v1", "SCHEMA")
    require(b.get("source_commit") == "af4a9e896328386723e8bbb957f334e1d83fe75e", "SOURCE")
    require(b.get("run_id") == 43587161603, "RUN")
    require(b.get("science") == "SCIENCE_HOLD", "SCIENCE")
    require(b.get("reference_role") == "PUBLIC_DIAGNOSTIC_REGRESSION_ONLY", "ROLE")
    require(b.get("reference_timestamp") == "UNKNOWN", "REFERENCE_TIME")
    require(b.get("reference_coordinates") == "ASSUMED_R_0_TO_25_Z_0_TO_44_CM", "REFERENCE_COORDINATES")
    require(b.get("physics_mode") == "chemistry_hybrid_json_native", "MODE")
    require(b.get("expected_frames") == 461 and b.get("expected_end_s") == 0.0001, "FRAMES")
    check_retention(b)
    require(set(b.get("cases", {})) == {"417", "941"}, "CASE_SET")
    for case in ("417", "941"):
        r = b["cases"][case]
        require(r.get("artifact_id") == {"417": 14117371106, "941": 14120049502}[case], "ARTIFACT_ID")
        require(r.get("archive_sha256") == ZIP_SHA[case], "ARTIFACT_SHA")
        require(r.get("archive_bytes", 0) > 90_000_000, "ARTIFACT_SIZE")
        require(r.get("archive_results_prefix") == f"_temp/hybrid_S6_{case}/results/", "PREFIX")
        needed = {"status.json", "manifest.json", "plasma.e", "plasma.csv",
                  "reference_comparison/metrics.json", f"unified_s6_{case}.json"}
        require(set(r.get("output_sha256", {})) == needed, "OUTPUT_SET")
        require(set(r.get("log_sha256", {})) == {"native_P2.log", "native_P3.log"}, "LOG_SET")
        for h in list(r["output_sha256"].values()) + list(r["log_sha256"].values()):
            require(bool(re.fullmatch(r"[0-9a-f]{64}", str(h))), "OUTPUT_SHA")
    return b

def check_semantics(b, case, r, status, manifest, metrics, p1):
    for obj in (status, manifest, p1):
        require(obj.get("source_sha") == b["source_commit"], "SOURCE_MISMATCH")
        require(obj.get("science") == "SCIENCE_HOLD", "SCIENCE_ACCEPTANCE_UNAUTHORIZED")
    for obj in (status, manifest):
        require(obj.get("case") == case and obj.get("arm") == "D", "CASE_MISMATCH")
        require(obj.get("physics_mode") == b["physics_mode"], "HYBRID_MODE_MISMATCH")
        require(obj.get("P3") == "PASS", "P3_NOT_PASSED")
        require(obj.get("oci_image") == r["oci_image"], "OCI_MISMATCH")
    for key, value in {"P0": "PASS", "P1": "PASS_SOURCE_BOUND_BINARY", "P2": "PASS",
                       "P3": "PASS", "P4": "DIAGNOSTIC_ONLY",
                       "status": "PASS_P3_REFERENCE_DIAGNOSTIC"}.items():
        require(status.get(key) == value, "STATUS_CHANGED:" + key)
    require(status.get("binary_sha256") == p1.get("binary_sha256") ==
            r["binary_sha256"] and p1.get("P1") == "PASS", "P1_BINARY_MISMATCH")
    require(p1.get("oci_image") == r["oci_image"], "P1_OCI_MISMATCH")
    cf = status.get("canonical_fields", {})
    require(cf.get("frames") == 461 and cf.get("electron_energy") == "log_e_energy", "CANONICAL_FIELDS")
    require(cf.get("elemental_ions") == ["log_O2p", "log_Om", "log_Op"], "ION_STATES")
    require(status.get("scratch_chemistry_cutover", {}).get("removed_count") == 9, "RETIRED_CHEMISTRY_OWNERS")
    h = status.get("hybrid_json_ownership_cutover", {})
    require(h.get("removed_generated_owner_count") == 10, "RETIRED_ELECTRON_OWNERS")
    require(h.get("rebound_native_sheath_bc_count") == 8, "SURVIVING_NATIVE_SHEATH")
    require(h.get("native_owner_preservation") ==
            "NATIVE_EQUATIONS_UNCHANGED_WITH_ROOT_PRESSURE_IC_AND_SPECIES_FUNCTORS",
            "SURVIVING_NATIVE_EQUATIONS")
    require(h.get("integrated_species_count") == 7 and
            h.get("integrated_reaction_count") == 8, "INTEGRATED_MECHANISM")
    require(h.get("hybrid_json_sha256") ==
            r["output_sha256"][f"unified_s6_{case}.json"], "JSON_SOURCE_MISMATCH")
    require(h.get("native_species_coefficient_binding_migration", {}).get(
            "constant_values_unchanged") is True, "ION_TRANSPORT_CHANGED")
    require(metrics.get("comparison_status") == "DIAGNOSTIC_ONLY" and
            metrics.get("science") == "SCIENCE_HOLD", "P4_NOT_DIAGNOSTIC")
    require(metrics.get("case") == case and metrics.get("native_p3") == "PASS", "P4_CASE")
    require(metrics.get("reference_timestamp") == b["reference_timestamp"] and
            metrics.get("reference_coordinates") == b["reference_coordinates"], "REFERENCE_ASSUMPTIONS")
    for key, measured in (
        ("native_peak_over_reference_peak", metrics.get("native_peak_over_reference_peak")),
        ("horizontal_relative_l2", metrics.get("horizontal", {}).get("relative_l2")),
        ("vertical_relative_l2", metrics.get("vertical", {}).get("relative_l2"))
    ):
        require(isinstance(measured, (int, float)) and math.isfinite(measured) and
                math.isclose(measured, r["p4"][key], rel_tol=0, abs_tol=1e-14),
                "REFERENCE_DIAGNOSTIC_CHANGED:" + key)

def read_json(z, name):
    require(z.getinfo(name).file_size < 1024 * 1024, "JSON_TOO_LARGE")
    return json.loads(z.read(name))

def verify_csv(z, name, r, b):
    with z.open(name) as stream:
        rows = csv.reader(io.TextIOWrapper(stream, encoding="utf-8", newline=""))
        header = next(rows)
        require(header[0] == "time" and len(header) == r["csv_columns"] and
                len(set(header)) == len(header), "CSV_SCHEMA")
        previous = float("-inf")
        count = 0
        for row in rows:
            require(len(row) == len(header), "CSV_ROW_WIDTH")
            values = [float(x) for x in row]
            require(all(math.isfinite(v) for v in values), "CSV_NONFINITE")
            require(values[0] > previous, "CSV_NONMONOTONIC_TIME")
            if count == 0:
                require(abs(values[0]) < 1e-15, "CSV_START")
            previous = values[0]
            count += 1
        require(count == b["expected_frames"], "CSV_FRAME_COUNT")
        require(abs(previous - b["expected_end_s"]) < 1e-12, "CSV_END_TIME")

def verify_case(archive, case, b):
    r = b["cases"][case]
    require(archive.is_file() and archive.stat().st_size == r["archive_bytes"], "ZIP_BYTES")
    require(file_sha(archive) == ZIP_SHA[case], "ZIP_SHA_CHANGED")
    prefix = r["archive_results_prefix"]
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)), "ZIP_DUPLICATE_NAMES")
        require(all(not n.startswith("/") and "\\" not in n and
                    all(p not in ("", "..") for p in n.split("/")) for n in names),
                "ZIP_UNSAFE_MEMBER")
        files = {name: prefix + name for name in r["output_sha256"]}
        logs = {name: f"_temp/hybrid_S6_{case}/{name}" for name in r["log_sha256"]}
        require(set(files.values()) | set(logs.values()) | {r["p1_identity_path"]}
                <= set(names), "ZIP_REQUIRED_FILES")
        for name, path in {**files, **logs}.items():
            expect = r["output_sha256"].get(name, r["log_sha256"].get(name))
            require(member_sha(z, path) == expect, "NESTED_SHA_CHANGED:" + name)
        status = read_json(z, files["status.json"])
        manifest = read_json(z, files["manifest.json"])
        metrics = read_json(z, files["reference_comparison/metrics.json"])
        p1 = read_json(z, r["p1_identity_path"])
        check_semantics(b, case, r, status, manifest, metrics, p1)
        for name, key in (("plasma.e", "native_exodus_sha256"),
                          ("plasma.csv", "native_csv_sha256")):
            require(status.get(key) == manifest.get("files", {}).get(name, {}).get("sha256")
                    == r["output_sha256"][name], "NATIVE_OUTPUT_SHA_CHANGED:" + name)
        mechanism_name = f"unified_s6_{case}.json"
        require(manifest.get("files", {}).get(mechanism_name, {}).get("sha256")
                == r["output_sha256"][mechanism_name], "JSON_MANIFEST_SHA")
        for gate in ("P2", "P3"):
            name = f"native_{gate}.log"
            require(status.get(f"p{gate[-1]}_log_sha256") ==
                    r["log_sha256"][name], "NATIVE_LOG_SHA:" + gate)
        require(b"Syntax OK" in z.read(logs["native_P2.log"]), "P2_SYNTAX_MISSING")
        require(b"Finished Executing" in z.read(logs["native_P3.log"]), "P3_FINISH_MISSING")
        mech = read_json(z, files[mechanism_name])
        require(len(mech["species"]) == 7 and len(mech["reactions"]) == 8 and
                set(mech["equations"]) == {x["id"] for x in mech["reactions"]},
                "MECHANISM_IDENTITY")
        verify_csv(z, files["plasma.csv"], r, b)
        # Reuse the original main read-only evidence verifier; no solver invoked.
        require(EXISTING.is_file(), "CANONICAL_VERIFIER_MISSING")
        spec = importlib.util.spec_from_file_location("issue402_canonical_p3", EXISTING)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix=f"issue402-s6-{case}-") as tmp:
            out = Path(tmp) / "results"
            for name, member in files.items():
                dest = out / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as inp, dest.open("wb") as target:
                    shutil.copyfileobj(inp, target, length=1024 * 1024)
            result = module.verify(out, b["source_commit"], case, hybrid_json=True)
            require(result.get("status") ==
                    "BYTES_AND_PROVENANCE_PASS_UPLOAD_RECEIPT_PENDING",
                    "CANONICAL_VERIFIER_REJECTED")
    return {"case": case, "artifact_id": r["artifact_id"],
            "result": "REFERENCE_BYTES_AND_P3_P4_DIAGNOSTIC_VERIFIED",
            "science": "SCIENCE_HOLD"}

def self_test(b):
    invalid = deepcopy(b)
    invalid["science"] = "ACCEPTED"
    try:
        require(invalid["science"] == "SCIENCE_HOLD", "SCIENCE_MUTATION")
    except ReferenceError:
        pass
    else:
        raise AssertionError("SCIENCE_MUTATION_NOT_DETECTED")
    r = b["cases"]["417"]
    status = {"source_sha": b["source_commit"], "science": "SCIENCE_HOLD",
              "case": "417", "arm": "D", "physics_mode": b["physics_mode"],
              "oci_image": r["oci_image"], "P0": "PASS", "P1": "PASS_SOURCE_BOUND_BINARY",
              "P2": "PASS", "P3": "PASS", "P4": "DIAGNOSTIC_ONLY",
              "status": "PASS_P3_REFERENCE_DIAGNOSTIC",
              "binary_sha256": r["binary_sha256"],
              "canonical_fields": {"frames": 461, "electron_energy": "log_e_energy",
                                   "elemental_ions": ["log_O2p", "log_Om", "log_Op"]},
              "scratch_chemistry_cutover": {"removed_count": 9},
              "hybrid_json_ownership_cutover": {"removed_generated_owner_count": 10,
                  "rebound_native_sheath_bc_count": 8, "integrated_species_count": 7,
                  "integrated_reaction_count": 8,
                  "native_owner_preservation":
                     "NATIVE_EQUATIONS_UNCHANGED_WITH_ROOT_PRESSURE_IC_AND_SPECIES_FUNCTORS",
                  "hybrid_json_sha256": r["output_sha256"]["unified_s6_417.json"],
                  "native_species_coefficient_binding_migration":
                     {"constant_values_unchanged": True}}}
    native = {k: status[k] for k in ("source_sha", "science", "case", "arm",
                                   "physics_mode", "P3", "oci_image")}
    p1 = {"source_sha": b["source_commit"], "science": "SCIENCE_HOLD",
          "P1": "PASS", "binary_sha256": r["binary_sha256"], "oci_image": r["oci_image"]}
    metric = {"comparison_status": "DIAGNOSTIC_ONLY", "science": "SCIENCE_HOLD",
              "native_p3": "PASS", "case": "417",
              "reference_timestamp": b["reference_timestamp"],
              "reference_coordinates": b["reference_coordinates"],
              "native_peak_over_reference_peak":
                 r["p4"]["native_peak_over_reference_peak"],
              "horizontal": {"relative_l2": r["p4"]["horizontal_relative_l2"]},
              "vertical": {"relative_l2": r["p4"]["vertical_relative_l2"]}}
    check_semantics(b, "417", r, status, native, metric, p1)
    for key, changed in (("P3", "NOT_RUN"), ("P4", "SCIENCE_ACCEPTED"),
                         ("source_sha", "0"*40), ("science", "SCIENCE_ACCEPTED")):
        bad = deepcopy(status)
        bad[key] = changed
        try:
            check_semantics(b, "417", r, bad, native, metric, p1)
        except ReferenceError:
            pass
        else:
            raise AssertionError("STATUS_MUTATION_NOT_DETECTED:" + key)
    for name in ("removed_generated_owner_count", "rebound_native_sheath_bc_count"):
        bad = deepcopy(status)
        bad["hybrid_json_ownership_cutover"][name] = 0
        try:
            check_semantics(b, "417", r, bad, native, metric, p1)
        except ReferenceError:
            pass
        else:
            raise AssertionError("OWNER_MUTATION_NOT_DETECTED:" + name)
    # The private ARCH readback must be independently evidenced and must
    # never imply a proven maintained full P3/P4 replay or science acceptance.
    check_retention(b)
    for label, keypath, altered in (
        ("BACKUP_UNPROVEN", ("retention", "durable_backup"), "NOT_PROVEN"),
        ("BACKUP_PUBLIC", ("retention", "independent_copy", "visibility"), "PUBLIC"),
        ("BACKUP_MISSING", ("cases", "417", "independent_copy", "url"), ""),
        ("BACKUP_TAMPER", ("cases", "941", "independent_copy", "readback_sha256"), "0"*64),
        ("BACKUP_SIZE_TAMPER", ("cases", "417", "independent_copy", "readback_bytes"), 0),
        ("REPLAY_PROMOTION", ("retention", "replay_contract", "unique_100us_two_case_p3_p4"), "RETIRED"),
        ("SCIENCE_PROMOTION", ("retention", "replay_contract", "science"), "ACCEPTED"),
    ):
        bad = deepcopy(b)
        target = bad
        for part in keypath[:-1]:
            target = target[part]
        target[keypath[-1]] = altered
        try:
            check_retention(bad)
        except ReferenceError:
            pass
        else:
            raise AssertionError("RETENTION_MUTATION_UNDETECTED:" + label)
    print("ISSUE402_S6_RETENTION_READBACK_MUTATION_SELF_TEST=PASS")
    print("ISSUE402_S6_REFERENCE_MUTATION_SELF_TEST=PASS")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--artifact417", type=Path)
    parser.add_argument("--artifact941", type=Path)
    args = parser.parse_args()
    require(bool(args.artifact417) == bool(args.artifact941), "BOTH_ARTIFACTS_REQUIRED")
    require(args.manifest_check or args.self_test or args.artifact417, "MISSING_CHECK")
    b = load_receipt()
    if args.self_test:
        self_test(b)
    if args.manifest_check:
        print("ISSUE402_S6_REFERENCE_MANIFEST_CONTRACT=PASS")
    if args.artifact417:
        print(json.dumps(verify_case(args.artifact417, "417", b), sort_keys=True))
        print(json.dumps(verify_case(args.artifact941, "941", b), sort_keys=True))
        print("ISSUE402_S6_REFERENCE_417_941_READ_ONLY=PASS; P4=DIAGNOSTIC_ONLY; SCIENCE=HOLD")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReferenceError, KeyError, ValueError, zipfile.BadZipFile) as error:
        print("ISSUE402_S6_REFERENCE=FAIL:", error, file=sys.stderr)
        raise SystemExit(1)
