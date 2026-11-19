#!/usr/bin/env python3
"""Code7 PR-A: exact-HEAD read-only FDEG evidence; never authorizes deletion."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import fdeg_structural as structural
import fdeg_functional as functional
import fdeg_transition as transition

TARGET = "PhysicsFVThermalDiffusion"
ROOT = Path(__file__).resolve().parents[2]
SOURCE = "physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C"
HEADER = "physics_app/include/fvkernels/PhysicsFVThermalDiffusion.h"


def generate(root: Path, expected_head: str, output_dir: Path) -> dict:
    root = root.resolve()
    if structural.git(root, "rev-parse", "HEAD") != expected_head:
        raise ValueError("CODE7_EXACT_HEAD_MISMATCH")
    if structural.git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("CODE7_TRACKED_WORKTREE_DIRTY")

    s = structural.scan(root, TARGET, expected_head)
    registry = functional.load_registry(root)
    f = functional.assemble(root, s, TARGET, registry, expected_head)
    policy, policy_sha = transition.load_policy(root)
    t = transition.assemble(root, s, f, TARGET, policy, policy_sha, expected_head)

    if s["target"] != TARGET or f["target"] != TARGET or t["target"] != TARGET:
        raise ValueError("CODE7_TARGET_MISMATCH")
    if f["source_identity"]["structural_graph_id"] != s["graph_id"]:
        raise ValueError("CODE7_STRUCTURAL_GRAPH_JOIN_MISMATCH")
    if t["source_identity"]["functional_graph_id"] != f["graph_id"]:
        raise ValueError("CODE7_FUNCTIONAL_GRAPH_JOIN_MISMATCH")
    if t["source_identity"]["structural_graph_id"] != s["graph_id"]:
        raise ValueError("CODE7_TRANSITION_GRAPH_JOIN_MISMATCH")
    if any(x["source_identity"]["repository_head"] != expected_head for x in (f, t)):
        raise ValueError("CODE7_HEAD_JOIN_MISMATCH")
    if (t["safe_delete"] != "HOLD" or t["caller_zero"] != "NOT_PROVEN"
            or t["runtime_observation"] != "NOT_OBSERVED"
            or t["numerical_equivalence"] != "NOT_PROVEN"):
        raise ValueError("CODE7_UNSUPPORTED_RETIREMENT_PROMOTION")
    if t["target_strategy"] != "RETAIN_NO_APPROVED_REPLACEMENT":
        raise ValueError("CODE7_UNAPPROVED_REPLACEMENT_STRATEGY")
    protected = policy["profiles"][TARGET]["protected"]
    if "NVTRANSPORTMATERIAL_D_T_PRODUCER" not in protected:
        raise ValueError("CODE7_DT_PRODUCER_PROTECTION_MISSING")

    source_blob = structural.blob_sha((root / SOURCE).read_bytes())
    header_blob = structural.blob_sha((root / HEADER).read_bytes())
    if f["source_identity"]["source_blobs"].get(SOURCE) != source_blob:
        raise ValueError("CODE7_SOURCE_BLOB_MISMATCH")
    counts = dict(sorted(Counter(x["kind"] for x in t["blocking_obligations"]).items()))
    roles = dict(sorted(Counter(x["role"] for x in f["consumer_contracts"]).items()))
    dispositions = dict(sorted(Counter(x["disposition"] for x in t["consumer_dispositions"]).items()))
    snapshot = {
        "schema": "code7.retirement_pra.v0.1",
        "target": TARGET,
        "repository_head": expected_head,
        "source_blobs": {SOURCE: source_blob, HEADER: header_blob},
        "graph_ids": {"structural": s["graph_id"], "functional": f["graph_id"],
                      "transition": t["graph_id"]},
        "schema_versions": {"structural": s["schema"], "functional": f["schema"],
                            "transition": t["schema"]},
        "scan_scope": s["scan_scope"],
        "structural_status": s["status"],
        "structural_instances": len(s["instances"]),
        "structural_edges": len(s["edges"]),
        "structural_unresolved_global": len(s["unresolved"]),
        "structural_unresolved_target": len(s["target_scoped_unresolved"]),
        "functional_consumer_roles": roles,
        "transition_consumer_dispositions": dispositions,
        "transition_blockers_by_kind": counts,
        "transition_blocker_count": len(t["blocking_obligations"]),
        "producer_preserve": "NVTRANSPORTMATERIAL_D_T_PRODUCER",
        "historical_factory_separate": "QPXFVThermalDiffusion",
        "runtime_observation": t["runtime_observation"],
        "numerical_equivalence": t["numerical_equivalence"],
        "caller_zero": t["caller_zero"],
        "safe_delete": t["safe_delete"],
        "scope_limit": "Tracked-source P0 only: no executed/generated-input, external-caller, or Native proof",
        "retirement_lifecycle": "OPEN: active source-pinned FDEG profile must be archived before C/H removal",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, report in (("structural.json", s), ("functional.json", f),
                         ("transition.json", t), ("summary.json", snapshot)):
        (output_dir / name).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        summary = generate(Path(args.root), args.expected_head, Path(args.output_dir))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("CODE7_FDEG_P0=FAIL:" + str(exc))
        return 1
    print("CODE7_FDEG_P0=PASS")
    print("CODE7_RETIREMENT=HOLD")
    print("CODE7_FDEG_SUMMARY=" + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
