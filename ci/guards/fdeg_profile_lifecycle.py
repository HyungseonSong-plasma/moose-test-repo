#!/usr/bin/env python3
"""FDEG code1 profile lifecycle guard; does not authorize deletion."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fdeg_structural as structural

ROOT = Path(__file__).resolve().parents[2]
META = Path("ci/baselines/fdeg_profile_lifecycle.json")
ARCHIVE = Path("ci/baselines/fdeg_historical_profiles_code1.json")


def load(root: Path = ROOT) -> tuple[dict, dict]:
    meta = json.loads((root / META).read_text(encoding="utf-8"))
    if meta.get("historical_profile_file") != ARCHIVE.as_posix():
        raise ValueError("LIFECYCLE_ARCHIVE_PATH_INVALID")
    raw = (root / ARCHIVE).read_bytes()
    if structural.blob_sha(raw) != meta.get("historical_profile_blob_sha"):
        raise ValueError("LIFECYCLE_ARCHIVE_BLOB_CHANGED")
    return meta, json.loads(raw)


def validate(root: Path = ROOT, meta: dict | None = None,
             archive: dict | None = None) -> dict:
    root = root.resolve()
    existing_meta, existing_archive = load(root)
    meta = copy.deepcopy(existing_meta if meta is None else meta)
    archive = copy.deepcopy(existing_archive if archive is None else archive)
    if archive != existing_archive:
        raise ValueError("LIFECYCLE_ARCHIVE_CONTENT_MISMATCH")
    if (meta.get("schema") != "fdeg.profile_lifecycle.v0.1"
            or archive.get("schema") != "fdeg.historical_profiles.v0.1"):
        raise ValueError("LIFECYCLE_SCHEMA_INVALID")
    target = meta.get("target")
    if target != "FVElectronResponseBandedCorrection":
        raise ValueError("LIFECYCLE_TARGET_INVALID")
    captured = archive.get("capture", {})
    if (captured.get("target") != target
            or captured.get("baseline_commit") != meta.get("baseline_commit")
            or len(str(meta.get("baseline_commit", ""))) != 40):
        raise ValueError("LIFECYCLE_BASELINE_IDENTITY_MISMATCH")
    source, header = captured["source_file"], captured["header_file"]
    if (archive.get("functional_profile", {}).get("target") != target
            or archive.get("transition_profile", {}).get("target") != target
            or archive["functional_profile"].get("source") != source):
        raise ValueError("LIFECYCLE_ARCHIVED_CONTRACT_MISMATCH")
    if captured.get("historical_qualification_scope") != "BOTH_LANES_USED_KERNEL_NOT_KERNEL_REMOVAL_PARITY":
        raise ValueError("LIFECYCLE_HISTORICAL_PARITY_FALSE_PROMOTION")
    if (meta.get("scientific_equivalence") != "NOT_PROVEN"
            or meta.get("historical_replay") != "PRESERVE_PINNED_SEPARATELY"):
        raise ValueError("LIFECYCLE_EQUIVALENCE_FALSE_PROMOTION")
    active_f = json.loads((root / "ci/baselines/fdeg_functional_contracts.json").read_text())
    active_t = json.loads((root / "ci/baselines/fdeg_transition_contracts.json").read_text())
    active_functional = active_f.get("profiles", {}).get(target)
    active_transition = active_t.get("profiles", {}).get(target)
    status = meta.get("status")
    if status == "PRE_RETIREMENT":
        if (meta.get("current_implementation") != "PRESENT"
                or meta.get("removal_approval") != "NOT_GRANTED"
                or meta.get("source_removal_in_this_pr") is not False
                or meta.get("retirement_receipt") is not None):
            raise ValueError("LIFECYCLE_PRE_RETIREMENT_SCOPE_INVALID")
        if active_functional != archive["functional_profile"]:
            raise ValueError("LIFECYCLE_ACTIVE_FUNCTIONAL_DIFFERS_FROM_ARCHIVE")
        if active_transition != archive["transition_profile"]:
            raise ValueError("LIFECYCLE_ACTIVE_TRANSITION_DIFFERS_FROM_ARCHIVE")
        for record in (source, header):
            file = root / record["path"]
            if not file.is_file() or structural.blob_sha(file.read_bytes()) != record["blob_sha"]:
                raise ValueError("LIFECYCLE_ACTIVE_SOURCE_BLOB_CHANGED:" + record["path"])
    elif status == "RETIRED":
        if (any((root / rec["path"]).exists() for rec in (source, header))
                or active_functional is not None or active_transition is not None):
            raise ValueError("LIFECYCLE_RETIRED_BUT_IMPLEMENTATION_ACTIVE")
        receipt = meta.get("retirement_receipt")
        if (not isinstance(receipt, dict) or not receipt.get("approval_ref")
                or not receipt.get("native_validation_ref")
                or not receipt.get("post_change_commit")):
            raise ValueError("LIFECYCLE_RETIREMENT_RECEIPT_REQUIRED")
        if meta.get("removal_approval") != "EXPLICIT_OWNER_APPROVAL":
            raise ValueError("LIFECYCLE_RETIRED_WITHOUT_APPROVAL")
    else:
        raise ValueError("LIFECYCLE_UNKNOWN_STATUS")
    return {"schema":meta["schema"],"target":target,"baseline_commit":meta["baseline_commit"],
            "lifecycle_status":status,"archive_blob_sha":meta["historical_profile_blob_sha"],
            "retirement_authorized_by_guard":False,
            "status":"PROFILE_LIFECYCLE_RECORDED"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        report = validate(args.root)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("FDEG_PROFILE_LIFECYCLE=FAIL:" + str(exc))
        return 1
    print(json.dumps(report, sort_keys=True))
    print("FDEG_PROFILE_LIFECYCLE=PASS_NOT_RETIREMENT_AUTHORIZATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
