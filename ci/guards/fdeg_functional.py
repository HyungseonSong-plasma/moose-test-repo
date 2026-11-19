#!/usr/bin/env python3
"""FDEG Functional v0.1: verified source contracts, not an equivalence/deletion gate.

Consumes a Structural v0.2 evidence document and a reviewed, exact-blob-pinned
semantic contract registry. Source observation is not runtime observation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fdeg_structural as structural  # noqa: E402

SCHEMA = "fdeg.functional.v0.1"
REGISTRY = Path("ci/baselines/fdeg_functional_contracts.json")
STRUCTURAL_SCHEMA = "fdeg.structural.v0.2"


def safe_path(root: Path, rel: str) -> Path:
    if not isinstance(rel, str) or not rel or PurePosixPath(rel).is_absolute():
        raise ValueError("UNSAFE_EVIDENCE_PATH")
    if ".." in PurePosixPath(rel).parts or str(PurePosixPath(rel)) != rel:
        raise ValueError("UNSAFE_EVIDENCE_PATH")
    return root / rel


def load_registry(root: Path, registry_path: Path = REGISTRY) -> dict:
    text = safe_path(root, registry_path.as_posix()).read_text(encoding="utf-8")
    doc = json.loads(text)
    if doc.get("schema") != "fdeg.functional_registry.v0.1" or not isinstance(doc.get("profiles"), dict):
        raise ValueError("FUNCTIONAL_REGISTRY_SCHEMA")
    return doc


def verify_structural(root: Path, report: dict, target: str,
                      expected_head: str | None = None) -> None:
    if report.get("schema") != STRUCTURAL_SCHEMA or report.get("target") != target:
        raise ValueError("STRUCTURAL_SCHEMA_OR_TARGET_MISMATCH")
    if not isinstance(report.get("edges"), list) or not isinstance(report.get("nodes"), list):
        raise ValueError("STRUCTURAL_GRAPH_MALFORMED")
    if not isinstance(report.get("instances"), list):
        raise ValueError("STRUCTURAL_INSTANCES_MISSING")
    original = {key: value for key, value in report.items() if key != "graph_id"}
    if structural.stable_id("graph", original) != report.get("graph_id"):
        raise ValueError("STRUCTURAL_GRAPH_ID_MISMATCH")
    head = report.get("repository_head")
    if expected_head is not None and head != expected_head:
        raise ValueError("STRUCTURAL_EXACT_HEAD_MISMATCH")
    if (root / ".git").exists():
        actual_head = structural.git(root, "rev-parse", "HEAD")
        if head != actual_head:
            raise ValueError("STRUCTURAL_STALE_REPOSITORY_HEAD")
        if structural.git(root, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError("STRUCTURAL_DIRTY_TRACKED_WORKTREE")
    elif head is not None or expected_head is not None:
        raise ValueError("STRUCTURAL_REPOSITORY_IDENTITY_NOT_AVAILABLE")
    nodes = [n.get("id") for n in report["nodes"] if isinstance(n, dict)]
    if len(nodes) != len(set(nodes)) or "class:" + target not in nodes:
        raise ValueError("STRUCTURAL_TARGET_NODE_OR_ID_COLLISION")
    node_set = set(nodes)
    edge_ids = set()
    cache: dict[str, tuple[list[str], str]] = {}
    for edge in report["edges"]:
        if not isinstance(edge, dict):
            raise ValueError("STRUCTURAL_EDGE_MALFORMED")
        identity = edge.get("edge_id")
        data = {key: value for key, value in edge.items() if key != "edge_id"}
        if identity != structural.stable_id("edge", data) or identity in edge_ids:
            raise ValueError("STRUCTURAL_EDGE_ID_MISMATCH")
        edge_ids.add(identity)
        if edge.get("from") not in node_set or edge.get("to") not in node_set:
            raise ValueError("STRUCTURAL_DANGLING_EDGE")
        ev = edge.get("evidence")
        if not isinstance(ev, dict) or not isinstance(ev.get("line"), int):
            raise ValueError("STRUCTURAL_EVIDENCE_MALFORMED")
        path = ev.get("path")
        if path not in cache:
            try:
                data = safe_path(root, path).read_bytes()
                cache[path] = (data.decode("utf-8").splitlines(), structural.blob_sha(data))
            except (OSError, UnicodeError) as exc:
                raise ValueError("STRUCTURAL_WITNESS_READ_FAILURE") from exc
        lines, sha = cache[path]
        line = ev["line"]
        if (sha != ev.get("blob_sha") or line < 1 or line > len(lines)
                or lines[line - 1].strip()[:240] != ev.get("excerpt")):
            raise ValueError("STRUCTURAL_WITNESS_MISMATCH")
    for instance in report["instances"]:
        if instance.get("instance_id") not in node_set:
            raise ValueError("STRUCTURAL_INSTANCE_NODE_MISSING")
        if instance.get("structural_edge_id") not in edge_ids:
            raise ValueError("STRUCTURAL_INSTANCE_EDGE_MISSING")
        if not isinstance(instance.get("bindings"), list):
            raise ValueError("STRUCTURAL_BINDINGS_MALFORMED")


def source_witnesses(root: Path, profile: dict) -> tuple[list[dict], dict]:
    """Verify pinned source bytes before accepting any source-supported claim."""
    source = profile.get("source")
    if not isinstance(source, dict):
        raise ValueError("FUNCTIONAL_SOURCE_IDENTITY_MISSING")
    blobs: dict[str, str] = {}
    witnesses: list[dict] = []
    for claim in profile.get("claims", []):
        anchors = claim.get("anchors")
        if (not isinstance(claim, dict) or not isinstance(claim.get("id"), str)
                or not isinstance(anchors, list) or not anchors
                or not all(isinstance(a, str) and a for a in anchors)):
            raise ValueError("FUNCTIONAL_CLAIM_SCHEMA")
        origin = claim.get("source", source)
        path, expected_blob = origin.get("path"), origin.get("blob_sha")
        if not isinstance(expected_blob, str) or len(expected_blob) != 40:
            raise ValueError("FUNCTIONAL_SOURCE_IDENTITY_MISSING")
        try:
            raw = safe_path(root, path).read_bytes()
            decoded = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError("FUNCTIONAL_SOURCE_READ_FAILED") from exc
        sha = structural.blob_sha(raw)
        if sha != expected_blob:
            raise ValueError("STALE_FUNCTIONAL_PROFILE_SOURCE_BLOB:" + path)
        blobs[path] = sha
        for anchor in anchors:
            offset = decoded.find(anchor)
            if offset < 0:
                raise ValueError("FUNCTIONAL_SOURCE_ANCHOR_MISSING:" + claim["id"])
            line_start = decoded.count("\n", 0, offset) + 1
            line_end = line_start + anchor.count("\n")
            witnesses.append({
                "claim_id": claim["id"], "path": path, "blob_sha": sha,
                "line_start": line_start, "line_end": line_end,
                "excerpt": anchor[:240], "match_count": decoded.count(anchor)})
    main_source = source.get("path")
    if main_source not in blobs:
        # Even a helper-only profile must independently attest its owning C++ source.
        raw = safe_path(root, main_source).read_bytes()
        if structural.blob_sha(raw) != source.get("blob_sha"):
            raise ValueError("STALE_FUNCTIONAL_PROFILE_SOURCE_BLOB:" + main_source)
        blobs[main_source] = source["blob_sha"]
    return witnesses, blobs


def validate_registry_profile(profile: dict) -> None:
    ids = [claim.get("id") for claim in profile.get("claims", [])]
    if not ids or len(set(ids)) != len(ids) or any(not isinstance(x, str) or not x for x in ids):
        raise ValueError("FUNCTIONAL_CLAIM_ID_COLLISION_OR_MISSING")
    for claim in profile["claims"]:
        for name in ("relation", "to", "expression"):
            if not isinstance(claim.get(name), str) or not claim[name]:
                raise ValueError("FUNCTIONAL_CLAIM_FIELD_MISSING:" + name)
        if claim.get("evidence_kind") != "SOURCE_OBSERVATION":
            raise ValueError("FUNCTIONAL_SOURCE_CLAIM_UNSUPPORTED_PROVENANCE")
    for candidate in profile.get("alternatives", []):
        if candidate.get("status") != "CANDIDATE_UNVERIFIED":
            raise ValueError("FUNCTIONAL_ALTERNATIVE_CANNOT_ASSERT_EQUIVALENCE")


def consumer_role(edge: dict) -> str | None:
    relationship = edge["relation"]
    return {
        "INPUT_INSTANTIATES": "DECLARED_INPUT_NOT_RUNTIME",
        "INPUT_MATCHES_ACTION_SYNTAX": "DECLARED_ACTION_INPUT_NOT_RUNTIME",
        "ACTION_CREATES": "SOURCE_ACTION_FACTORY_CALL_NOT_RUNTIME",
        "ACTION_CREATES_VIA_LOCAL_LITERAL": "SOURCE_LEXICAL_FLOW_CANDIDATE",
        "CPP_CONSTRUCTS": "SOURCE_CPP_CONSTRUCTION_NOT_RUNTIME",
        "PYTHON_DECLARES_TYPE": "SOURCE_GENERATOR_DECLARATION_NOT_RUNTIME",
        "JSON_DECLARES_TYPE": "SOURCE_JSON_TYPE_NOT_RUNTIME",
        "MENTIONS_SYMBOL": "LEXICAL_MENTION_NOT_CONSUMER",
    }.get(relationship)


def assemble(root: Path, structural_report: dict, target: str, registry: dict,
             expected_head: str | None = None) -> dict:
    root = root.resolve()
    verify_structural(root, structural_report, target, expected_head)
    if registry.get("schema") != "fdeg.functional_registry.v0.1":
        raise ValueError("FUNCTIONAL_REGISTRY_SCHEMA")
    profile = registry.get("profiles", {}).get(target)
    if not isinstance(profile, dict) or profile.get("target") != target:
        raise ValueError("FUNCTIONAL_PROFILE_NOT_AVAILABLE:" + target)
    validate_registry_profile(profile)
    witnesses, blobs = source_witnesses(root, profile)
    registration = sorted(
        e["edge_id"] for e in structural_report["edges"]
        if e["to"] == "class:" + target and
        e["relation"] in {"REGISTERS", "REGISTERS_ACTION", "REGISTERS_PHYSICS_TASKS"})
    if not registration:
        raise ValueError("FUNCTIONAL_TARGET_REGISTRATION_NOT_PROVEN")
    instance_map = {x["instance_id"]: x for x in structural_report["instances"]}
    witness_map = {x["claim_id"]: [] for x in witnesses}
    for item in witnesses:
        witness_map[item["claim_id"]].append({k: v for k, v in item.items() if k != "claim_id"})

    functional_edges = []
    for claim in profile["claims"]:
        edge = {
            "claim_id": "claim:" + target + ":" + claim["id"],
            "from": "class:" + target, "relation": claim["relation"],
            "to": claim["to"], "expression": claim["expression"],
            "mode": claim.get("mode", "all"), "units": claim.get("units", "UNSPECIFIED"),
            "conditions": claim.get("conditions", []), "assumptions": claim.get("assumptions", []),
            "counterexamples": claim.get("counterexamples", []),
            "applicability": claim.get("applicability", "SOURCE_CLASS_ONLY"),
            "evidence_kind": "STATIC_SOURCE", "claim_status": "SOURCE_SUPPORTED",
            "runtime_status": "NOT_OBSERVED",
            "structural_registration_edge_ids": registration,
            "witnesses": sorted(witness_map[claim["id"]],
                                key=lambda w: (w["path"], w["line_start"], w["excerpt"]))
        }
        edge["edge_id"] = structural.stable_id("functional-edge", edge)
        functional_edges.append(edge)
    for candidate in profile.get("alternatives", []):
        edge = {
            "claim_id": "candidate:" + target + ":" + candidate["candidate_type"],
            "from": "class:" + target, "relation": "ALTERNATIVE_CANDIDATE",
            "to": "class:" + candidate["candidate_type"],
            "conditions": candidate.get("conditions", []),
            "counterexamples": candidate.get("semantic_risks", []),
            "required_proof": candidate.get("requires", "INDEPENDENT_PARITY_PROOF"),
            "evidence_kind": "REVIEW_REQUIREMENT_NOT_SOURCE_EQUIVALENCE",
            "claim_status": "CANDIDATE_UNVERIFIED",
            "runtime_status": "NOT_OBSERVED", "witnesses": []
        }
        edge["edge_id"] = structural.stable_id("functional-edge", edge)
        functional_edges.append(edge)
    functional_edges.sort(key=lambda e: (e["relation"], e["to"], e["claim_id"]))

    consumers = []
    for edge in structural_report["edges"]:
        if edge["to"] != "class:" + target:
            continue
        role = consumer_role(edge)
        if role is None:
            continue
        instance = instance_map.get(edge["from"])
        consumers.append({
            "structural_edge_id": edge["edge_id"], "source_node": edge["from"],
            "role": role, "evidence_strength": edge["strength"],
            "instance_id": instance["instance_id"] if instance else None,
            "declared_bindings": instance["bindings"] if instance else [],
            "effective_runtime_binding": "NOT_OBSERVED",
            "consumer_activation": "NOT_OBSERVED",
            "behavior_to_preserve": profile["capability"] if role != "LEXICAL_MENTION_NOT_CONSUMER" else None
        })
    consumers.sort(key=lambda c: (c["source_node"], c["structural_edge_id"]))
    unresolved = sorted(set(profile.get("unresolved_semantics", [])) |
                        ({"STRUCTURAL_SCAN_INCOMPLETE"} if structural_report["status"] == "INCOMPLETE" else set()))
    report = {
        "schema": SCHEMA, "target": target,
        "source_identity": {
            "repository_head": structural_report["repository_head"],
            "structural_schema": structural_report["schema"],
            "structural_graph_id": structural_report["graph_id"],
            "source_blobs": dict(sorted(blobs.items())),
            "registry_schema": registry["schema"]},
        "capability": profile["capability"], "equation": profile["equation"],
        "operator_kind": profile["operator_kind"], "notes": profile.get("notes", ""),
        "edges": functional_edges,
        "consumer_contracts": consumers,
        "required_discriminators": sorted(profile.get("required_discriminators", [])),
        "discriminator_evidence_status": "NOT_EVALUATED",
        "historical_guards": sorted(profile.get("historical_guards", [])),
        "unresolved_obligations": unresolved,
        "runtime_observation": "NOT_OBSERVED",
        "equivalence_verdict": "NOT_PROVEN",
        "status": "FUNCTIONAL_SOURCE_RECORDED_WITH_OPEN_OBLIGATIONS",
        "safety": "NO_CALLER_ZERO_TRANSITION_OR_RETIREMENT_AUTHORIZATION"}
    report["graph_id"] = structural.stable_id("functional-graph", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--structural", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.structural.read_text(encoding="utf-8"))
        result = assemble(args.root, data, args.target, load_registry(args.root),
                          args.expected_head)
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
        print("FDEG_FUNCTIONAL_P0=FAIL:" + str(exc))
        return 1
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
        print("FDEG_FUNCTIONAL_REPORT=" + str(args.output))
    else:
        print(rendered, end="")
    print("FDEG_FUNCTIONAL_P0=PASS")
    print("FDEG_RETIREMENT=HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
