#!/usr/bin/env python3
"""Code4 PR-A: summarize pinned FDEG evidence without promoting any deletion claim.

Consumes only Structural v0.3, Functional v0.2, Transition v0.1 JSON.
Read-only: emits a manifest and prints a bounded review summary.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


TARGET = "PhysicsFVElectrostaticDrift"


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object in {path}")
    return value


def assemble(s: dict, f: dict, t: dict, head: str) -> dict:
    if (s.get("schema"), f.get("schema"), t.get("schema")) != (
        "fdeg.structural.v0.3", "fdeg.functional.v0.2", "fdeg.transition.v0.1"
    ):
        raise ValueError("FDEG_SCHEMA_MISMATCH")
    if any(report.get("target") != TARGET for report in (s, f, t)):
        raise ValueError("FDEG_TARGET_MISMATCH")
    fs = f.get("source_identity", {})
    ts = t.get("source_identity", {})
    if not (
        s.get("repository_head") == head
        == fs.get("repository_head") == ts.get("repository_head")
        and s.get("graph_id") == fs.get("structural_graph_id")
        == ts.get("structural_graph_id")
        and f.get("graph_id") == ts.get("functional_graph_id")
    ):
        raise ValueError("FDEG_CROSS_GRAPH_IDENTITY_MISMATCH")
    if (t.get("safe_delete") != "HOLD"
            or t.get("execution_status") != "NOT_EXECUTED"
            or t.get("numerical_equivalence") != "NOT_PROVEN"):
        raise ValueError("UNSAFE_TRANSITION_STATUS")

    consumers = []
    for c in t.get("consumer_dispositions", []):
        consumers.append({
            "structural_edge_id": c.get("structural_edge_id"),
            "instance_id": c.get("instance_id"),
            "source_node": c.get("source_node"),
            "input_path": c.get("input_path"),
            "block_path": c.get("block_path"),
            "role": c.get("role"),
            "reference_scope": c.get("reference_scope"),
            "disposition": c.get("disposition"),
            "proposed_action": c.get("disposition_proposal"),
            "before": c.get("before"),
            "blocking_obligation_ids": c.get("blocking_obligation_ids", []),
        })
    consumers.sort(key=lambda item: item["structural_edge_id"] or "")

    blockers = t.get("blocking_obligations", [])
    workflow_steps = []
    for step in t.get("steps", []):
        workflow_steps.append({
            "step_id": step.get("step_id"),
            "operation": step.get("operation"),
            "consumer_id": step.get("consumer_id"),
            "depends_on_steps": step.get("depends_on_steps", []),
            "affected_paths": step.get("affected_paths", []),
            "eligible_to_execute": step.get("eligible_to_execute"),
            "verification_gates": [g.get("gate") for g in step.get("verification_gates", [])],
        })
    summary = {
        "schema": "code4.retirement_pr_a_evidence.v0.1",
        "target": TARGET,
        "source_head": head,
        "analysis_status": "PINNED_GRAPH_REVIEW_ONLY",
        "safe_delete": "HOLD",
        "graphs": {
            "structural": s.get("graph_id"),
            "functional": f.get("graph_id"),
            "transition": t.get("graph_id"),
        },
        "structural_status": s.get("status"),
        "structural_counts": {
            "edges": len(s.get("edges", [])),
            "instances": len(s.get("instances", [])),
            "generator_routes": len(s.get("enrichment", {}).get("generator_routes", [])),
            "provider_bindings": len(s.get("enrichment", {}).get("provider_bindings", [])),
            "target_scoped_unresolved": len(s.get("target_scoped_unresolved", [])),
            "scan_errors": len(s.get("scan_errors", [])),
        },
        "consumer_role_counts": dict(sorted(Counter(x.get("role") for x in consumers).items())),
        "consumer_disposition_counts": dict(sorted(Counter(x.get("disposition") for x in consumers).items())),
        "consumer_records": consumers,
        "generator_routes": f.get("generator_consumer_routes", []),
        "producer_binding_graph": f.get("producer_binding_graph", []),
        "change_sites": t.get("change_sites", {}),
        "protected_resources": t.get("protected_resources", []),
        "historical_gates": t.get("historical_gates", []),
        "candidate_options": [
            {"type": x.get("candidate_type"), "status": x.get("status"),
             "transition_permission": x.get("transition_permission"),
             "parameter_mapping_proposal": x.get("parameter_mapping_proposal")}
            for x in t.get("candidate_rewiring_options", [])
        ],
        "blocking_kind_counts": dict(sorted(Counter(b.get("kind") for b in blockers).items())),
        "blocking_obligations": blockers,
        "workflow_steps": workflow_steps,
        "explicit_nonclaims": [
            "NO_RUNTIME_ACTIVATION_PROOF",
            "NO_COMPLETE_EXTERNAL_CALLER_CENSUS",
            "NO_APPROVED_REPLACEMENT_PARITY",
            "NO_NATIVE_RESIDUAL_OR_JACOBIAN_PARITY",
            "NO_RETIREMENT_AUTHORIZATION",
        ],
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--structural", required=True, type=Path)
    parser.add_argument("--functional", required=True, type=Path)
    parser.add_argument("--transition", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summary = assemble(read_json(args.structural), read_json(args.functional),
                       read_json(args.transition), args.expected_head)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    brief = {
        key: summary[key] for key in (
            "schema", "source_head", "graphs", "structural_status",
            "structural_counts", "consumer_role_counts",
            "consumer_disposition_counts", "change_sites",
            "protected_resources", "historical_gates", "candidate_options",
            "blocking_kind_counts", "safe_delete"
        )
    }
    brief["consumers"] = [
        {key: item[key] for key in (
            "input_path", "block_path", "role", "reference_scope",
            "disposition", "proposed_action", "instance_id", "structural_edge_id"
        )} for item in summary["consumer_records"]
    ]
    print("CODE4_PR_A_SUMMARY_BEGIN")
    print(json.dumps(brief, sort_keys=True, separators=(",", ":")))
    print("CODE4_PR_A_SUMMARY_END")
    print("CODE4_PR_A_STATUS=EVIDENCE_ONLY_SAFE_DELETE_HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
