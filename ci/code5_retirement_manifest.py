#!/usr/bin/env python3
"""code5-A: exact-HEAD Structural/Functional/Transition evidence and file-level HOLD manifest.

Read-only evidence generation. This is not a migration executor or deletion gate.
Run from a clean checkout of a pinned commit; outputs should be stored outside Git.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci" / "guards"))
import fdeg_structural as structural  # noqa: E402
import fdeg_functional as functional  # noqa: E402
import fdeg_transition as transition  # noqa: E402

SHARED_C = "physics_app/src/fvkernels/PhysicsFVLogMolarElectronTransport.C"
SHARED_H = "physics_app/include/fvkernels/PhysicsFVLogMolarElectronTransport.h"
TARGETS = (
    "PhysicsFVLogMolarElectronTimeDerivative",
    "PhysicsFVLogMolarElectronDiffusion",
    "PhysicsFVLogMolarElectrostaticDrift",
    "PhysicsFVLogMolarElectronReactionSource",
)

# Historical/canonical status is not inferred correctly from filesystem prefixes
# in Structural v0.3. Keep these known families on manual, no-edit review.
ROLE_REVIEW_PREFIXES = (
    "experiments/Issue3_dielectric_surface_charge/",
    "experiments/Issue402_plasma_dsl_g1/native/",
)


def disposition(consumer: dict) -> str:
    """Conservative actionable role, layered on unobserved Transition v0.1."""
    role = consumer.get("role")
    path = consumer.get("input_path") or ""
    if role == "LEXICAL_MENTION_NOT_CONSUMER":
        return "REFERENCE_ONLY_NO_EDIT"
    if consumer.get("disposition") == "PRESERVE_HISTORICAL":
        return "PRESERVE_HISTORICAL_NO_EDIT"
    if any(path.startswith(prefix) for prefix in ROLE_REVIEW_PREFIXES):
        return "CANONICAL_OR_HISTORICAL_ROLE_REVIEW_NO_EDIT"
    if not consumer.get("instance_id"):
        return "GENERATOR_ACTION_OR_REFERENCE_REVIEW_NO_EDIT"
    if not path.endswith(".i"):
        return "NON_INPUT_SITE_REVIEW_NO_EDIT"
    return "REWIRE_CANDIDATE_UNVERIFIED"


def build_manifest(head: str, reports: dict[str, tuple[dict, dict, dict]]) -> dict:
    if set(reports) != set(TARGETS):
        raise ValueError("CODE5_MISSING_OR_EXTRA_CLASS_PROFILE")
    if not head or len(head) != 40:
        raise ValueError("CODE5_HEAD_INVALID")

    consumers, obligations, targets, candidate_sites = [], [], [], set()
    all_paths, generated_sites, workflow_sites = set(), set(), set()
    source_blobs = set()
    header_blobs = set()
    for target in TARGETS:
        s, f, t = reports[target]
        identity = t.get("source_identity", {})
        if (s.get("target") != target or f.get("target") != target
                or t.get("target") != target
                or s.get("repository_head") != head
                or f.get("source_identity", {}).get("repository_head") != head
                or identity.get("repository_head") != head
                or identity.get("structural_graph_id") != s.get("graph_id")
                or identity.get("functional_graph_id") != f.get("graph_id")):
            raise ValueError("CODE5_CROSS_GRAPH_IDENTITY_MISMATCH:" + target)
        shared = t.get("shared_owner_contract")
        if (not shared or shared.get("source_path") != SHARED_C
                or set(shared.get("co_registered_classes", [])) != set(TARGETS)
                or t.get("safe_delete") != "HOLD"
                or t.get("plan_status") != "CONDITIONAL_PLAN"
                or t.get("execution_status") != "NOT_EXECUTED"
                or any(x.get("eligible_to_execute") for x in t.get("steps", []))):
            raise ValueError("CODE5_OWNER_OR_SAFETY_GATE_INVALID:" + target)
        blob = f.get("source_identity", {}).get("source_blobs", {}).get(SHARED_C)
        if not blob:
            raise ValueError("CODE5_SOURCE_BLOB_MISSING:" + target)
        source_blobs.add(blob)
        local_header_blobs = {
            e.get("evidence", {}).get("blob_sha")
            for e in s.get("edges", [])
            if e.get("evidence", {}).get("path") == SHARED_H
        }
        if len(local_header_blobs) != 1 or not next(iter(local_header_blobs)):
            raise ValueError("CODE5_SHARED_HEADER_WITNESS_MISSING_OR_AMBIGUOUS:" + target)
        header_blobs.update(local_header_blobs)
        change = t.get("change_sites", {})
        all_paths.update(change.get("declared_input_and_other_consumer_paths", []))
        generated_sites.update(change.get("generator_paths", []))
        generated_sites.update(change.get("generated_output_candidates_not_observed", []))
        workflow_sites.update(change.get("workflow_paths", []))
        counts = {}
        for c in t.get("consumer_dispositions", []):
            status = disposition(c)
            counts[status] = counts.get(status, 0) + 1
            record = {
                "target": target,
                "consumer_id": c["consumer_id"],
                "structural_edge_id": c["structural_edge_id"],
                "instance_id": c.get("instance_id"),
                "input_path": c.get("input_path"),
                "block_path": c.get("block_path"),
                "role": c.get("role"),
                "reference_scope": c.get("reference_scope"),
                "transition_disposition": c["disposition"],
                "code5_disposition": status,
                "before": c.get("before", {}),
                "after_proposal": c.get("after_proposal", {}),
                "functional_claim_ids": c.get("functional_claim_ids", []),
                "execution_status": "NOT_EXECUTED",
            }
            consumers.append(record)
            if status == "REWIRE_CANDIDATE_UNVERIFIED":
                candidate_sites.add(c["input_path"])
        for b in t.get("blocking_obligations", []):
            obligations.append({
                "target": target,
                "obligation_id": b["obligation_id"],
                "kind": b["kind"],
                "consumer": b.get("consumer"),
                "required_evidence": b["required_evidence"],
                "gate": b["gate"],
                "oracle": b["oracle"],
                "owner": b["owner"],
                "status": b["status"],
                "origin_ref": b["origin_ref"],
            })
        targets.append({
            "target": target,
            "source_blob_sha": blob,
            "graph_ids": {
                "structural": s["graph_id"],
                "functional": f["graph_id"],
                "transition": t["graph_id"],
            },
            "reports": {
                "structural": target + ".structural.json",
                "functional": target + ".functional.json",
                "transition": target + ".transition.json",
            },
            "structural_status": s["status"],
            "functional_status": f["status"],
            "transition_status": t["plan_status"],
            "candidate_options": [
                x["candidate_type"] for x in t.get("candidate_rewiring_options", [])
            ],
            "disposition_counts": dict(sorted(counts.items())),
            "blocking_obligation_count": len(t.get("blocking_obligations", [])),
            "owner_gate": "NOT_DISCHARGED",
        })
    if len(source_blobs) != 1:
        raise ValueError("CODE5_SHARED_SOURCE_BLOB_DIVERGED")
    if len(header_blobs) != 1:
        raise ValueError("CODE5_SHARED_HEADER_BLOB_DIVERGED")
    consumers.sort(key=lambda x: (x["target"], x["structural_edge_id"]))
    obligations.sort(key=lambda x: (x["target"], x["obligation_id"]))
    manifest = {
        "schema": "code5.retirement_manifest.v0.1",
        "repository_head": head,
        "scope": "FOUR_CLASS_SHARED_CPP_TRANSLATION_UNIT",
        "source_path": SHARED_C,
        "header_path": SHARED_H,
        "source_blob_sha": next(iter(source_blobs)),
        "header_blob_sha": next(iter(header_blobs)),
        "owners": list(TARGETS),
        "targets": targets,
        "consumers": consumers,
        "blocking_obligations": obligations,
        "change_sites": {
            "all_declared_or_reference_paths_NOT_AN_EDIT_LIST": sorted(all_paths),
            "rewire_candidates_NOT_APPROVED": sorted(candidate_sites),
            "generator_or_unobserved_output_review": sorted(generated_sites),
            "workflow_static_declarations": sorted(workflow_sites),
            "protected_role_prefixes": list(ROLE_REVIEW_PREFIXES),
        },
        "required_gates": [
            "RESOLVE_CANONICAL_VS_HISTORICAL_CONSUMER_ROLES",
            "QUALIFY_GENERIC_KERNEL_SOURCE_AT_EXACT_HEAD_AND_P1_BUILD",
            "OBSERVE_EFFECTIVE_GENERATORS_FUNCTORS_AND_NATIVE_OBJECTS",
            "MATCH_RESIDUAL_FLUX_TIME_AD_AND_REACTION_SOURCE_ORACLES",
            "KEEP_ORIGINAL_D6_AND_S6_HISTORY_SEPARATE_FROM_NEWONLY",
            "VERIFY_FOUR_OF_FOUR_FACTORY_OWNER_DISPOSITION",
            "REBUILD_PRE_POST_GRAPH_AND_VERIFY_NO_MISSING_DOUBLE_TERMS",
            "REBASE_CI_AND_FDEG_RETIRED_PROFILE_BEFORE_REMOVAL",
            "EXACT_HEAD_POST_CHANGE_CI_AND_NATIVE_VALIDATION",
            "COVERAGE_SCOPE_AND_EXPLICIT_DOMAIN_APPROVAL_SEPARATE",
        ],
        "unverified_harness_limitations": [
            "PATH_HEURISTIC_DOES_NOT_CLASSIFY_D6_OR_S6_C0_AS_HISTORICAL",
            "TRANSITION_AGGREGATE_CHANGE_SITES_INCLUDE_REFERENCE_ONLY",
            "NO_EXECUTED_GRAPH_ONLY_INDEPENDENT_ACCEPTANCE",
            "UNOBSERVED_DYNAMIC_GENERATED_EXTERNAL_AND_FUNCTOR_BINDINGS",
        ],
        "evidence_grade": "STATIC_SOURCE_BOUND",
        "graph_only_acceptance": "NOT_EVALUATED",
        "numeric_parity": "NOT_EVALUATED",
        "runtime_activation": "NOT_OBSERVED",
        "coverage": "NOT_PROVEN",
        "caller_zero": "NOT_PROVEN",
        "all_four_owner_gates": "BLOCKED",
        "transition_execution": "NOT_EXECUTED",
        "safe_delete": "HOLD",
    }
    manifest["manifest_id"] = structural.stable_id("code5-manifest", manifest)
    return manifest


def produce(root: Path, head: str, output: Path) -> dict:
    root = root.resolve()
    if structural.git(root, "rev-parse", "HEAD") != head:
        raise ValueError("CODE5_EXACT_HEAD_MISMATCH")
    if structural.git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("CODE5_DIRTY_TRACKED_WORKTREE")
    registry = functional.load_registry(root)
    policy, policy_sha = transition.load_policy(root)
    reports = {}
    # No report is written until source-bound construction succeeds for all targets.
    for target in TARGETS:
        s = structural.scan(root, target, head)
        f = functional.assemble(root, s, target, registry, head)
        t = transition.assemble(root, s, f, target, policy, policy_sha, head)
        reports[target] = (s, f, t)
    manifest = build_manifest(head, reports)
    output.mkdir(parents=True, exist_ok=True)
    for target, (s, f, t) in reports.items():
        for suffix, report in (("structural", s), ("functional", f), ("transition", t)):
            (output / (target + "." + suffix + ".json")).write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "code5-retirement-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = produce(ROOT, args.expected_head, args.output_dir)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("CODE5_A_EVIDENCE=FAIL:" + str(exc), file=sys.stderr)
        return 1
    print("CODE5_A_EVIDENCE=GENERATED")
    print("CODE5_A_MANIFEST_ID=" + manifest["manifest_id"])
    print("CODE5_A_TARGETS=" + str(len(manifest["targets"])))
    print("CODE5_A_CONSUMERS=" + str(len(manifest["consumers"])))
    print("CODE5_A_BLOCKERS=" + str(len(manifest["blocking_obligations"])))
    print("CODE5_A_SAFE_DELETE=HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
