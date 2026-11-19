#!/usr/bin/env python3
"""Source-bound pre-retirement receipts and post-retirement STATIC guards.

No C++ mutation, science acceptance, caller-zero or deletion authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fdeg_structural as structural  # noqa: E402
import fdeg_functional as functional  # noqa: E402
import fdeg_transition as transition  # noqa: E402

SCHEMA = "fdeg.retirement_receipt.v0.1"
RETIRED_SCHEMA = "fdeg.retired_review.v0.1"
GRAPH_NAMES = ("structural", "functional", "transition")


def canonical(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def capture(root: Path, target: str, expected_head: str) -> tuple[dict, dict[str, dict]]:
    """Regenerate three graphs from exactly one clean HEAD; capture is NOT PASS parity."""
    s = structural.scan(root, target, expected_head)
    f = functional.assemble(root, s, target, functional.load_registry(root), expected_head)
    policy, policy_blob = transition.load_policy(root)
    t = transition.assemble(root, s, f, target, policy, policy_blob, expected_head)
    if t.get("safe_delete") != "HOLD" or t.get("execution_status") != "NOT_EXECUTED":
        raise ValueError("RETIREMENT_UNSAFE_TRANSITION_STATE")
    graphs = {"structural": s, "functional": f, "transition": t}
    blobs = {}
    profile = functional.load_registry(root)["profiles"][target]
    paths = [profile["source"]["path"]]
    for item in s.get("enrichment", {}).get("shared_translation_units", []):
        if item["source_path"] not in paths:
            paths.append(item["source_path"])
    for edge in s["edges"]:
        if edge["relation"] == "HEADER_DECLARES_TARGET":
            paths.append(edge["evidence"]["path"])
    for path in sorted(set(paths)):
        source = functional.safe_path(root, path).read_bytes()
        blobs[path] = structural.blob_sha(source)
    manifest = {
        "schema": SCHEMA,
        "target": target, "lifecycle": "PRE_RETIREMENT",
        "baseline_head": expected_head,
        "graph_ids": {name: graphs[name]["graph_id"] for name in GRAPH_NAMES},
        "graph_sha256": {name: sha256(canonical(graphs[name])) for name in GRAPH_NAMES},
        "source_blobs": dict(sorted(blobs.items())),
        "registered_owners": (t.get("shared_owner_aggregate_requirement") or {}).get(
            "registered_classes", [target]),
        "global_scan_status": s["status"],
        "target_dependency_status": s.get("target_dependency_status", "UNKNOWN"),
        "target_scoped_unresolved": s["target_scoped_unresolved"],
        "blocking_obligation_ids": sorted(b["obligation_id"]
                                          for b in t["blocking_obligations"]),
        "historical_receipt_policy": "PRESERVE_IMMUTABLY_SEPARATE_FROM_CURRENT_BINARY",
        "historical_protected_blobs": {},  # Only explicitly pre-pinned paths may be exempted.
        "actual_runtime_activation": "NOT_OBSERVED",
        "actual_caller_zero": "NOT_PROVEN",
        "discriminator_acceptance": "NOT_EVALUATED",
        "physics_parity": "NOT_PROVEN",
        "safe_delete": "HOLD",
        "meaning": "PRE_RETIREMENT_EVIDENCE_ONLY_NOT_RETIREMENT_AUTHORIZATION",
    }
    manifest["manifest_sha256"] = sha256(canonical(manifest))
    return manifest, graphs


def verify_snapshot(receipt: dict, graphs: dict[str, dict]) -> None:
    """Prevent a forged/missing input graph or broken archive from being accepted."""
    if receipt.get("schema") != SCHEMA or receipt.get("lifecycle") != "PRE_RETIREMENT":
        raise ValueError("RETIREMENT_RECEIPT_SCHEMA_OR_STATE")
    if set(graphs) != set(GRAPH_NAMES):
        raise ValueError("RETIREMENT_MISSING_GRAPH")
    original = {k: v for k, v in receipt.items() if k != "manifest_sha256"}
    if receipt.get("manifest_sha256") != sha256(canonical(original)):
        raise ValueError("RETIREMENT_RECEIPT_MUTATED")
    for name in GRAPH_NAMES:
        doc = graphs[name]
        if doc.get("graph_id") != receipt["graph_ids"][name]:
            raise ValueError("RETIREMENT_GRAPH_ID_MISMATCH:" + name)
        if sha256(canonical(doc)) != receipt["graph_sha256"][name]:
            raise ValueError("RETIREMENT_GRAPH_CONTENT_MISMATCH:" + name)
    if (graphs["structural"].get("repository_head") != receipt["baseline_head"]
            or graphs["functional"].get("source_identity", {}).get("repository_head")
            != receipt["baseline_head"]
            or graphs["transition"].get("source_identity", {}).get("repository_head")
            != receipt["baseline_head"]):
        raise ValueError("RETIREMENT_GRAPH_HEAD_MISMATCH")
    if (graphs["functional"]["source_identity"]["structural_graph_id"]
            != graphs["structural"]["graph_id"]
            or graphs["transition"]["source_identity"]["structural_graph_id"]
            != graphs["structural"]["graph_id"]
            or graphs["transition"]["source_identity"]["functional_graph_id"]
            != graphs["functional"]["graph_id"]):
        raise ValueError("RETIREMENT_GRAPH_JOIN_MISMATCH")
    if (graphs["transition"].get("safe_delete") != "HOLD"
            or receipt.get("safe_delete") != "HOLD"):
        raise ValueError("RETIREMENT_FALSE_DELETE_PROMOTION")


def verify_retired(root: Path, receipt: dict, review: dict, expected_head: str) -> dict:
    """Post-cut static guard. Never accepts a no-receipt or incomplete owner claim."""
    if receipt.get("schema") != SCHEMA or receipt.get("lifecycle") != "PRE_RETIREMENT":
        raise ValueError("RETIREMENT_MISSING_PRE_CUT_RECEIPT")
    original = {k: v for k, v in receipt.items() if k != "manifest_sha256"}
    if sha256(canonical(original)) != receipt.get("manifest_sha256"):
        raise ValueError("RETIREMENT_PRE_CUT_RECEIPT_TAMPERED")
    if review.get("schema") != RETIRED_SCHEMA or review.get("state") != "RETIRED":
        raise ValueError("RETIREMENT_REVIEW_SCHEMA_OR_STATE")
    if (review.get("target") != receipt["target"]
            or review.get("baseline_manifest_sha256") != receipt["manifest_sha256"]
            or review.get("retirement_head") != expected_head):
        raise ValueError("RETIREMENT_REVIEW_IDENTITY_MISMATCH")
    required = ("owner_approval_ref", "independent_native_receipt_ref",
                "independent_coverage_receipt_ref",
                "current_binary_compatibility_decision_ref",
                "historical_archive_ref", "rollback_review_ref")
    if any(not isinstance(review.get(key), str) or not review[key].strip()
           or review[key] in {"UNKNOWN", "NOT_EVALUATED", "NOT_OBSERVED"}
           for key in required):
        raise ValueError("RETIREMENT_MISSING_INDEPENDENT_APPROVAL_RECEIPT")
    if not root.is_dir():
        raise ValueError("RETIREMENT_SOURCE_TREE_UNAVAILABLE")
    if (root / ".git").exists() and structural.git(root, "rev-parse", "HEAD") != expected_head:
        raise ValueError("RETIREMENT_STALE_EXACT_HEAD")
    remaining = sorted(path for path in receipt["source_blobs"]
                       if functional.safe_path(root, path).exists())
    if remaining:
        raise ValueError("RETIREMENT_SOURCE_STILL_PRESENT:" + ",".join(remaining))
    if set(review.get("discharged_registered_owners", [])) != set(receipt["registered_owners"]):
        raise ValueError("RETIREMENT_SHARED_OWNER_NOT_DISCHARGED")
    # The audit scope MUST be supplied by independent Coverage. A local-only
    # literal scan can disprove absence, but can never prove caller-zero.
    if review.get("external_and_generated_scope") != "INDEPENDENTLY_ATTESTED":
        raise ValueError("RETIREMENT_EXTERNAL_GENERATED_SCOPE_UNVERIFIED")
    protected = set(review.get("historical_protected_paths", []))
    pinned_historical = receipt.get("historical_protected_blobs", {})
    if not isinstance(pinned_historical, dict) or not protected <= set(pinned_historical):
        raise ValueError("RETIREMENT_HISTORICAL_PATH_NOT_PREPINNED")
    for path in protected:
        resolved = functional.safe_path(root, path)
        if not path.startswith(("archive/", "experiments/")):
            raise ValueError("RETIREMENT_HISTORICAL_EXEMPTION_UNSAFE")
        if not resolved.is_file() or structural.blob_sha(resolved.read_bytes()) != pinned_historical[path]:
            raise ValueError("RETIREMENT_HISTORICAL_BYTES_CHANGED")
    # Do not permit an old *active* registry entry to survive simply because
    # the scanner excludes immutable metadata from the current-consumer census.
    for registry_rel in ("ci/baselines/fdeg_functional_contracts.json",
                         "ci/baselines/fdeg_transition_contracts.json"):
        registry_file = functional.safe_path(root, registry_rel)
        if registry_file.exists():
            registry = json.loads(registry_file.read_text(encoding="utf-8"))
            if receipt["target"] in registry.get("profiles", {}):
                raise ValueError("RETIREMENT_ACTIVE_PROFILE_NOT_ARCHIVED:" + registry_rel)
    detected = []
    token = re.compile(r"\b" + re.escape(receipt["target"]) + r"\b")
    for file in structural.tracked_files(root)[0]:
        rel = file.relative_to(root).as_posix()
        if rel in protected:
            continue
        if rel.startswith(("ci/baselines/fdeg_", "docs/development/fdeg_",
                           "tests/test_fdeg_")):
            continue  # Evidence/guard source is not a current Physics consumer.
        if token.search(file.read_text(encoding="utf-8", errors="replace")):
            detected.append(rel)
    if detected:
        raise ValueError("RETIREMENT_SOURCE_SYMBOL_REINTRODUCED:" + ",".join(detected[:12]))
    return {
        "schema": RETIRED_SCHEMA,
        "state": "RETIRED_STATIC_GUARD_CONDITIONALLY_VERIFIED",
        "target": receipt["target"],
        "baseline_head": receipt["baseline_head"],
        "retirement_head": expected_head,
        "graph_archive_sha256": receipt["graph_sha256"],
        "independent_receipt_refs": {name: review[name] for name in required},
        "static_source_absence": "SOURCE_AND_REGISTERED_OWNER_ABSENT_WITHIN_TRACKED_SCOPE",
        "runtime_parity_reverified_here": "NOT_EVALUATED_BY_THIS_STATIC_GUARD",
        "caller_zero_reverified_here": "NOT_PROVEN_BY_THIS_STATIC_GUARD",
        "safe_delete": "HOLD",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--mode", choices=("capture", "verify-archive", "verify-retired"),
                        default="capture")
    parser.add_argument("--target", help="Target C++ class for capture")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--review", type=Path, help="Approved post-cut review JSON")
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if args.mode == "capture":
            if not args.target:
                raise ValueError("RETIREMENT_TARGET_REQUIRED")
            receipt, graphs = capture(root, args.target, args.expected_head)
            verify_snapshot(receipt, graphs)
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for name, doc in graphs.items():
                (args.output_dir / (name + ".json")).write_bytes(canonical(doc))
            (args.output_dir / "manifest.json").write_bytes(canonical(receipt))
            print("FDEG_RETIREMENT_SNAPSHOT=" + str(args.output_dir))
        else:
            receipt = json.loads((args.output_dir / "manifest.json").read_text())
            graphs = {name: json.loads((args.output_dir / (name + ".json")).read_text())
                      for name in GRAPH_NAMES}
            verify_snapshot(receipt, graphs)
            if args.mode == "verify-retired":
                if not args.review:
                    raise ValueError("RETIREMENT_POST_CUT_REVIEW_REQUIRED")
                review = json.loads(args.review.read_text())
                result = verify_retired(root, receipt, review, args.expected_head)
                (args.output_dir / "retired-guard.json").write_bytes(canonical(result))
            elif receipt["baseline_head"] != args.expected_head:
                raise ValueError("RETIREMENT_ARCHIVE_EXACT_HEAD_MISMATCH")
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("FDEG_RETIREMENT_EVIDENCE_P0=FAIL:" + str(exc))
        return 1
    print("FDEG_RETIREMENT_EVIDENCE_P0=PASS")
    print("FDEG_RETIREMENT=HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
