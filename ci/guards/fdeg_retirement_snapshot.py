#!/usr/bin/env python3
"""Capture exact-head FDEG pre-retirement graphs. This never authorizes deletion."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fdeg_structural as structural
import fdeg_functional as functional
import fdeg_transition as transition
import fdeg_profile_lifecycle as lifecycle


def serialized(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, indent=2) + "\n").encode("utf-8")


def capture(root: Path, target: str, head: str, output_dir: Path) -> dict:
    root = root.resolve()
    if target != "FVElectronResponseBandedCorrection":
        raise ValueError("SNAPSHOT_TARGET_UNSUPPORTED")
    if structural.git(root, "rev-parse", "HEAD") != head:
        raise ValueError("SNAPSHOT_EXACT_HEAD_MISMATCH")
    if structural.git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("SNAPSHOT_DIRTY_TRACKED_WORKTREE")
    state = lifecycle.validate(root)
    if state["lifecycle_status"] != "PRE_RETIREMENT":
        raise ValueError("SNAPSHOT_NOT_PRE_RETIREMENT")
    s = structural.scan(root, target, head)
    f = functional.assemble(root, s, target, functional.load_registry(root), head)
    policy, blob = transition.load_policy(root)
    t = transition.assemble(root, s, f, target, policy, blob, head)
    documents = {"structural.json":s, "functional.json":f, "transition.json":t}
    output_dir.mkdir(parents=True, exist_ok=True)
    digests = {}
    for filename, data in documents.items():
        payload = serialized(data)
        (output_dir / filename).write_bytes(payload)
        digests[filename] = {"sha256":hashlib.sha256(payload).hexdigest(),
                             "graph_id":data["graph_id"],"schema":data["schema"]}
    result = {
        "schema":"fdeg.retirement_preparation_snapshot.v0.1",
        "target":target,"repository_head":head,
        "pre_retirement_baseline_commit":state["baseline_commit"],
        "historical_archive_blob_sha":state["archive_blob_sha"],
        "graphs":digests,
        "structural_status":s["status"],
        "scan_errors":s.get("scan_errors", []),
        "target_scoped_unresolved":s.get("target_scoped_unresolved", []),
        "all_unresolved_count":len(s.get("unresolved", [])),
        "consumer_disposition_count":len(t["consumer_dispositions"]),
        "blocking_obligation_count":len(t["blocking_obligations"]),
        "blocking_obligation_kinds":sorted(set(x["kind"] for x in t["blocking_obligations"])),
        "transition_plan_status":t["plan_status"],
        "execution_status":t["execution_status"],
        "safe_delete":"HOLD",
        "historical_parity_is_removal_parity":False,
        "runtime_observed":False,
        "artifact_purpose":"EXACT_HEAD_P0_GRAPHS_NOT_NATIVE_OR_RETIREMENT_APPROVAL"
    }
    (output_dir / "manifest.json").write_bytes(serialized(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--target", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = capture(args.root, args.target, args.expected_head, args.output_dir)
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
        print("FDEG_CODE1_SNAPSHOT=FAIL:" + str(exc))
        return 1
    print(json.dumps(result, sort_keys=True))
    print("FDEG_CODE1_SNAPSHOT=CAPTURED_HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
