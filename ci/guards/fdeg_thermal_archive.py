#!/usr/bin/env python3
"""Verify pinned pre-retirement FDEG archive bytes without promoting deletion.

This is an archive-integrity gate, not a caller-closure, current binary
compatibility, physics parity, or safe-delete determination.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fdeg_retirement_evidence as retirement  # noqa: E402

SCHEMA = "fdeg.historical_archive_anchor.v0.1"
EXPECTED_FILES = ("functional.json", "manifest.json",
                  "structural.json", "transition.json")
MAX_ZIP_BYTES = 2 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024


def verify_archive_bytes(blob: bytes, anchor: dict) -> dict:
    """Verify ZIP identity, four immutable graphs and exact-head joins.

    The pinned ZIP may be independently downloaded from the historical
    workflow artifact. No live source checkout is required to check it.
    """
    if not isinstance(anchor, dict) or anchor.get("schema") != SCHEMA:
        raise ValueError("FDEG_ARCHIVE_ANCHOR_SCHEMA")
    if not isinstance(blob, bytes) or len(blob) > MAX_ZIP_BYTES:
        raise ValueError("FDEG_ARCHIVE_ZIP_SIZE")
    digest = hashlib.sha256(blob).hexdigest()
    if digest != anchor.get("artifact_zip_sha256"):
        raise ValueError("FDEG_ARCHIVE_ZIP_SHA_MISMATCH")

    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            infos = archive.infolist()
            if sorted(item.filename for item in infos) != list(EXPECTED_FILES):
                raise ValueError("FDEG_ARCHIVE_UNEXPECTED_ENTRIES")
            if sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("FDEG_ARCHIVE_UNCOMPRESSED_SIZE")
            decoded = {
                name: json.loads(archive.read(name).decode("utf-8"))
                for name in EXPECTED_FILES
            }
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("FDEG_ARCHIVE_INVALID_ZIP_OR_JSON") from exc

    receipt = decoded["manifest.json"]
    graphs = {name: decoded[name + ".json"]
              for name in retirement.GRAPH_NAMES}
    retirement.verify_snapshot(receipt, graphs)
    if (receipt.get("target") != anchor.get("target")
            or receipt.get("baseline_head") != anchor.get("baseline_head")
            or receipt.get("manifest_sha256") != anchor.get("manifest_sha256")
            or receipt.get("source_blobs") != anchor.get("source_blobs")
            or receipt.get("graph_sha256") != anchor.get("graph_sha256")):
        raise ValueError("FDEG_ARCHIVE_PINNED_IDENTITY_MISMATCH")
    if (receipt.get("actual_caller_zero") != "NOT_PROVEN"
            or receipt.get("actual_runtime_activation") != "NOT_OBSERVED"
            or receipt.get("physics_parity") != "NOT_PROVEN"
            or receipt.get("safe_delete") != "HOLD"):
        raise ValueError("FDEG_ARCHIVE_FALSE_APPROVAL")
    return {
        "schema": "fdeg.historical_archive_validation.v0.1",
        "target": receipt["target"],
        "baseline_head": receipt["baseline_head"],
        "manifest_sha256": receipt["manifest_sha256"],
        "archive_zip_sha256": digest,
        "source_blobs": receipt["source_blobs"],
        "graph_ids": receipt["graph_ids"],
        "archive_integrity": "PASS",
        "global_consumer_closed": False,
        "science_accepted": False,
        "safe_delete": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-zip", type=Path, required=True)
    parser.add_argument(
        "--anchor", type=Path,
        default=Path(__file__).resolve().parents[2]
        / "reports/issue774/fdeg_thermal_historical_anchor_v0_1.json"
    )
    args = parser.parse_args()
    try:
        if args.archive_zip.is_symlink() or not args.archive_zip.is_file():
            raise ValueError("FDEG_ARCHIVE_ZIP_MISSING_OR_SYMLINK")
        if args.archive_zip.stat().st_size > MAX_ZIP_BYTES:
            raise ValueError("FDEG_ARCHIVE_ZIP_SIZE")
        anchor = json.loads(args.anchor.read_text(encoding="utf-8"))
        result = verify_archive_bytes(args.archive_zip.read_bytes(), anchor)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("FDEG_PINNED_ARCHIVE=FAIL:" + str(exc))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    print("FDEG_PINNED_ARCHIVE=PASS")
    print("FDEG_RETIREMENT=HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
