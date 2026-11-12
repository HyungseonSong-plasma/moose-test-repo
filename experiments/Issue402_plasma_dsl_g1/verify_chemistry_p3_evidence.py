#!/usr/bin/env python3
"""Read-only post-P3 evidence integrity gate. No solver or artifact upload.

A PASS here is NOT a GitHub Actions artifact receipt or science acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def verify(results: Path, expected_head: str, case: str) -> dict:
    if case not in ("417", "941") or len(expected_head) != 40:
        raise ValueError("P3_EVIDENCE_INVALID_REQUEST")
    manifest = json.loads((results / "manifest.json").read_text())
    status = json.loads((results / "status.json").read_text())
    for obj in (status, manifest):
        if obj.get("case") != case or obj.get("arm") != "D":
            raise ValueError("P3_EVIDENCE_CASE_OR_ARM_MISMATCH")
        if obj.get("physics_mode") != "chemistry":
            raise ValueError("P3_EVIDENCE_NOT_CHEMISTRY")
        if obj.get("source_sha") != expected_head:
            raise ValueError("P3_EVIDENCE_SOURCE_MISMATCH")
        if obj.get("science") != "SCIENCE_HOLD":
            raise ValueError("P3_EVIDENCE_SCIENCE_STATUS_MISMATCH")
        if obj.get("P3") != "PASS":
            raise ValueError("P3_EVIDENCE_SOLVER_NOT_PASSED")
    if status.get("P2") != "PASS" or status.get("P0") != "PASS" or (
        status.get("P1") != "PASS_SOURCE_BOUND_BINARY"
    ):
        raise ValueError("P3_EVIDENCE_REQUIRED_GATES_NOT_PASSED")
    if status.get("P4") != "DIAGNOSTIC_ONLY" or (
        status.get("status") != "PASS_P3_REFERENCE_DIAGNOSTIC"
    ):
        raise ValueError("P3_EVIDENCE_P4_DIAGNOSTIC_INCOMPLETE")
    if status.get("canonical_fields", {}).get("frames") != 461 or (
        status.get("canonical_fields", {}).get("electron_energy") != "log_e_energy"
    ):
        raise ValueError("P3_EVIDENCE_CANONICAL_ENERGY_OR_TIME_MISMATCH")
    if status.get("scratch_chemistry_cutover", {}).get("removed_count") != 9:
        raise ValueError("P3_EVIDENCE_SUPERSEDED_OWNER_COUNT_MISMATCH")
    if not status.get("binary_sha256") or not status.get("sidecar_sha256") or (
        not status.get("p2_log_sha256") or not status.get("p3_log_sha256")
    ):
        raise ValueError("P3_EVIDENCE_PROVENANCE_MISSING")
    out = {}
    for filename, key in (("plasma.e", "native_exodus_sha256"),
                          ("plasma.csv", "native_csv_sha256")):
        path = results / filename
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("P3_EVIDENCE_MISSING_OUTPUT:" + filename)
        sha = digest(path)
        if sha != status.get(key) or sha != manifest.get("files", {}).get(filename, {}).get("sha256"):
            raise ValueError("P3_EVIDENCE_OUTPUT_SHA_MISMATCH:" + filename)
        out[filename] = sha
    return {"status": "BYTES_AND_PROVENANCE_PASS_UPLOAD_RECEIPT_PENDING",
            "case": case, "source_sha": expected_head, "files_sha256": out,
            "artifact_rest_receipt": "PENDING",
            "science": "SCIENCE_HOLD"}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--case", choices=("417", "941"), required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.results, args.expected_head, args.case),
                     sort_keys=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
