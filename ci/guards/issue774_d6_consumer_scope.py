#!/usr/bin/env python3
"""Exact-Git-tree consumer witness inventory for #774 D6 (not caller-zero proof).

Complements canonical Harness run_scan(); never replaces Graph coverage,
independent generated/external-consumer attestation or compatibility approval.
All findings are source-declared; no secret-bearing line text is exported.
"""
from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path
import re
import subprocess

TARGET = "PhysicsFVThermalDiffusion"
OTHER_APP = "QPXFVThermalDiffusion"
SOURCE = "physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C"
HEADER = "physics_app/include/fvkernels/PhysicsFVThermalDiffusion.h"
D6_SCHEMA = "fvkernel.d6.consumer_scope.v0.1"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
MOOSE_TYPE = re.compile(r"\btype\s*=\s*PhysicsFVThermalDiffusion\b")
CONFIG_DECL = re.compile(r"register(?:AD)?MooseObject\s*\(")


def _git(root: Path, *args: str, allow_no_matches: bool = False) -> bytes:
    run = subprocess.run(["git", "-C", str(root), *args],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         timeout=90, check=False)
    if run.returncode and not (allow_no_matches and run.returncode == 1):
        raise ValueError("D6_GIT_SOURCE_UNAVAILABLE")
    return run.stdout


def classify(path: str, *, has_target: bool, has_other_app: bool,
             direct_type: bool, active_profile: bool) -> str:
    """No location or exact-token match ever proves consumer absence."""
    if has_other_app and not has_target:
        return "DISTINCT_QPX_APP_KEEP_UNCHANGED"
    if path in (SOURCE, HEADER):
        return "RETIRED_SOURCE_REINTRODUCED"
    if path.startswith("physics_app/src/") or path.startswith("physics_app/include/"):
        return "ACTIVE_CXX_REFERENCE_REVIEW"
    if path.endswith(".i") or direct_type:
        return "MOOSE_INPUT_CONSUMER_REVIEW"
    if path.startswith(".github/workflows/"):
        return "LIVE_WORKFLOW_DEPENDENCY_REVIEW"
    if path.startswith("ci/baselines/fdeg_"):
        return "ACTIVE_FDEG_PROFILE_REVIEW" if active_profile else "FDEG_HISTORICAL_RECORD_REVIEW"
    if path.startswith(("tests/", "ci/guards/")):
        return "TEST_OR_GUARD_REFERENCE_REVIEW"
    if path.endswith((".py", ".sh")):
        return "GENERATOR_OR_SCRIPT_REFERENCE_REVIEW"
    if path.startswith(("reports/", "docs/", "archive/")):
        return "DOCUMENTED_EVIDENCE_REVIEW"
    return "UNCLASSIFIED_SOURCE_REFERENCE_HOLD"


def audit(root: Path, expected_head: str) -> dict:
    if not HEX40.fullmatch(expected_head):
        raise ValueError("D6_INVALID_HEAD")
    head = _git(root, "rev-parse", "--verify", "HEAD").decode().strip()
    if head != expected_head:
        raise ValueError("D6_EXACT_HEAD_MISMATCH")
    tree = _git(root, "rev-parse", "HEAD^{tree}").decode().strip()
    entries = _git(root, "ls-tree", "-r", "-l", "-z", "HEAD").split(b"\0")
    tracked = {}
    binary_or_nonregular = 0
    for entry in entries:
        if not entry:
            continue
        meta, rel = entry.split(b"\t", 1)
        mode, kind, blob_sha, size = meta.decode("ascii").split()
        path = rel.decode("utf-8")
        if path in tracked or kind != "blob":
            raise ValueError("D6_INVALID_GIT_TREE")
        tracked[path] = (blob_sha, mode, size)
        if mode not in ("100644", "100755") or path.endswith(
                (".zip", ".gz", ".xz", ".pdf", ".png", ".jpg", ".b64")):
            binary_or_nonregular += 1
    matches = _git(root, "grep", "-n", "-F", "-I",
                   "-e", TARGET, "-e", OTHER_APP, "HEAD", "--",
                   allow_no_matches=True)
    by_path = {}
    for row in matches.decode("utf-8").splitlines():
        # git grep <revision> output: HEAD:path:line:text.
        parts = row.split(":", 3)
        if len(parts) != 4 or parts[0] != "HEAD":
            raise ValueError("D6_GREP_FORMAT_UNEXPECTED")
        _, path, number, line = parts
        if path not in tracked or not number.isdecimal():
            raise ValueError("D6_GREP_NOT_IN_GIT_TREE")
        record = by_path.setdefault(path, {"target_lines": [], "other_app_lines": [],
                                           "direct_type": False})
        if TARGET in line:
            record["target_lines"].append(int(number))
            record["direct_type"] |= MOOSE_TYPE.search(line) is not None
        if OTHER_APP in line:
            record["other_app_lines"].append(int(number))
    rows = []
    for path, hits in sorted(by_path.items()):
        blob, mode, size = tracked[path]
        active_profile = False
        if path.startswith("ci/baselines/fdeg_") and path.endswith(".json"):
            data = _git(root, "show", "HEAD:" + path)
            doc = json.loads(data)
            active_profile = TARGET in doc.get("profiles", {})
        kind = classify(
            path, has_target=bool(hits["target_lines"]),
            has_other_app=bool(hits["other_app_lines"]),
            direct_type=hits["direct_type"], active_profile=active_profile)
        rows.append({
            "path": path, "git_blob_sha1": blob, "mode": mode, "bytes": size,
            "reference_class": kind, "target_line_numbers": hits["target_lines"],
            "distinct_qpx_line_numbers": hits["other_app_lines"],
            "active_fdeg_profile": active_profile,
            "classification_only_not_approval": True,
        })
    counts = dict(sorted(Counter(r["reference_class"] for r in rows).items()))
    if any(r["path"] in (SOURCE, HEADER) for r in rows):
        source_absent = False
    else:
        source_absent = SOURCE not in tracked and HEADER not in tracked
    return {
        "schema": D6_SCHEMA, "repository": "HyungseonSong-plasma/moose-test-repo",
        "source_head": head, "source_tree": tree,
        "tracked_path_count": len(tracked),
        "binary_or_nonregular_paths_not_content_scanned": binary_or_nonregular,
        "target": TARGET, "distinct_other_app_type": OTHER_APP,
        "source_and_header_absent": source_absent,
        "reference_paths": rows, "reference_class_counts": counts,
        "full_git_tree_token_inventory": True,
        "canonical_harness_run_scan_receipt_required": True,
        "generated_artifact_scope": "UNVERIFIED_EXTERNAL_OR_GENERATED_OUTPUTS",
        "current_binary_legacy_input_support": "OWNER_DECISION_NOT_ATTESTED",
        "independent_external_consumer_scope": "NOT_ATTESTED",
        "compatibility_decision": "HOLD", "safe_to_delete": False,
        "runtime_parity": "NOT_INFERRED_FROM_STATIC_REFERENCE_SCAN",
        "science": "SCIENCE_HOLD",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--expected-head", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    try:
        report = audit(args.root.resolve(), args.expected_head)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print("ISSUE774_D6_SOURCE_AUDIT=FAIL:" + str(exc))
        return 1
    print("ISSUE774_D6_SOURCE_AUDIT=SOURCE_DECLARATIONS_ONLY")
    print("ISSUE774_D6_REFERENCE_PATHS=" + str(len(report["reference_paths"])))
    print("ISSUE774_D6_COMPATIBILITY=HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
