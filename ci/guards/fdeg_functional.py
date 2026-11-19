#!/usr/bin/env python3
"""FDEG Functional v0.2: verified source contracts, not an equivalence/deletion gate.

Consumes a Structural v0.2 evidence document and a reviewed, exact-blob-pinned
semantic contract registry. Source observation is not runtime observation.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fdeg_structural as structural  # noqa: E402

SCHEMA = "fdeg.functional.v0.2"
REGISTRY = Path("ci/baselines/fdeg_functional_contracts.json")
STRUCTURAL_SCHEMA = "fdeg.structural.v0.3"
PARAM_DECL = re.compile(
    r'\bparams\.(addRequiredParam|addParam)<([^;]*?)>\s*\(\s*"([^"]+)"', re.S
)
PARAM_SET = re.compile(
    r'\bparams\.set<([^;]*?)>\s*\(\s*"([^"]+)"\s*\)\s*=\s*([^;]+);', re.S
)



def safe_path(root: Path, rel: str) -> Path:
    if not isinstance(rel, str) or not rel or PurePosixPath(rel).is_absolute():
        raise ValueError("UNSAFE_EVIDENCE_PATH")
    if ".." in PurePosixPath(rel).parts or str(PurePosixPath(rel)) != rel:
        raise ValueError("UNSAFE_EVIDENCE_PATH")
    return root / rel


def load_registry(root: Path, registry_path: Path = REGISTRY) -> dict:
    text = safe_path(root, registry_path.as_posix()).read_text(encoding="utf-8")
    doc = json.loads(text)
    if doc.get("schema") != "fdeg.functional_registry.v0.2" or not isinstance(doc.get("profiles"), dict):
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
    id_to_edge = {e["edge_id"]: e for e in report["edges"]}
    for instance in report["instances"]:
        instance_id = instance.get("instance_id")
        if instance_id not in node_set:
            raise ValueError("STRUCTURAL_INSTANCE_NODE_MISSING")
        if instance.get("structural_edge_id") not in edge_ids:
            raise ValueError("STRUCTURAL_INSTANCE_EDGE_MISSING")
        edge = id_to_edge[instance["structural_edge_id"]]
        allowed_relation = ("PYTHON_TEMPLATE_INSTANTIATES"
                            if instance.get("instance_kind") ==
                            "PYTHON_GENERATED_INPUT_TEMPLATE_NOT_EXECUTED"
                            else "INPUT_INSTANTIATES")
        if (edge["from"] != instance_id or edge["relation"] != allowed_relation
                or edge["to"] != "class:" + target):
            raise ValueError("STRUCTURAL_INSTANCE_EDGE_NOT_BOUND")
        if not isinstance(instance.get("bindings"), list):
            raise ValueError("STRUCTURAL_BINDINGS_MALFORMED")
        path = instance.get("input_path")
        if not isinstance(path, str):
            raise ValueError("STRUCTURAL_INSTANCE_SOURCE_MISSING")
        if path not in cache:
            try:
                data = safe_path(root, path).read_bytes()
                cache[path] = (data.decode("utf-8").splitlines(), structural.blob_sha(data))
            except (OSError, UnicodeError) as exc:
                raise ValueError("STRUCTURAL_INSTANCE_SOURCE_MISSING") from exc
        lines, blob = cache[path]
        type_line = instance.get("type_line")
        if (not isinstance(type_line, int) or type_line < 1 or type_line > len(lines)
                or blob != instance.get("evidence", {}).get("blob_sha")
                or edge["evidence"]["path"] != path
                or edge["evidence"]["line"] != type_line):
            raise ValueError("STRUCTURAL_INSTANCE_WITNESS_MISMATCH")
        type_assignment = structural.MOOSE_ASSIGN.match(lines[type_line - 1])
        if (not type_assignment or type_assignment.group(1) != "type"
                or type_assignment.group(2).strip().strip("'\"") != instance.get("factory_type")):
            raise ValueError("STRUCTURAL_INSTANCE_TYPE_MISMATCH")
        for binding in instance["bindings"]:
            line = binding.get("line")
            if not isinstance(line, int) or line < 1 or line > len(lines):
                raise ValueError("STRUCTURAL_BINDING_LINE_MISMATCH")
            match = structural.MOOSE_ASSIGN.match(lines[line - 1])
            if (not match or match.group(1) != binding.get("name")
                    or match.group(2).strip() != binding.get("raw_value")):
                raise ValueError("STRUCTURAL_BINDING_WITNESS_MISMATCH")

    # The graph ID alone is not authentication: an attacker could alter a
    # provider/generator candidate, rehash the report, and invent a dependency.
    # Source-byte reconstruction is required before trusting v0.3 enrichments.
    enrichment = report.get("enrichment")
    if (not isinstance(enrichment, dict) or
            not all(isinstance(enrichment.get(key), list) for key in (
                "build_ownership", "shared_translation_units", "generator_routes",
                "provider_bindings", "workflow_execution_paths", "external_imports"))):
        raise ValueError("STRUCTURAL_V03_ENRICHMENT_MALFORMED")
    rebuilt = structural.scan(root, target, expected_head)
    if rebuilt["graph_id"] != report["graph_id"]:
        raise ValueError("STRUCTURAL_ENRICHMENT_SOURCE_RECONSTRUCTION_MISMATCH")


def function_span(source: str, qualified: str) -> tuple[int, int]:
    """Locate a target C++ method's brace-delimited body in pinned source bytes."""
    name = re.escape(qualified)
    match = re.search(r'\b' + name + r'\s*\(\s*\)\s*', source)
    if match is None:
        raise ValueError("FUNCTIONAL_OWNER_FUNCTION_MISSING:" + qualified)
    start = source.find("{", match.end())
    if start < 0:
        raise ValueError("FUNCTIONAL_OWNER_FUNCTION_BODY_MISSING:" + qualified)
    depth = 0
    for offset in range(start, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return start, offset + 1
    raise ValueError("FUNCTIONAL_OWNER_FUNCTION_UNBALANCED:" + qualified)


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
        start, stop = (0, len(decoded))
        if claim.get("function_scope"):
            start, stop = function_span(decoded, claim["function_scope"])
        for anchor in anchors:
            offset = decoded.find(anchor, start, stop)
            if offset < 0 or offset + len(anchor) > stop:
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


def extract_parameters(root: Path, profile: dict) -> list[dict]:
    """Extract declarations and literal assignments; do NOT resolve MOOSE defaults."""
    source = profile["source"]
    path = source["path"]
    data = safe_path(root, path).read_bytes()
    blob = structural.blob_sha(data)
    if blob != source["blob_sha"]:
        raise ValueError("STALE_FUNCTIONAL_PROFILE_SOURCE_BLOB:" + path)
    body = data.decode("utf-8")
    start, stop = function_span(body, profile["target"] + "::validParams")
    segment = body[start:stop]
    params = []
    for match in PARAM_DECL.finditer(segment):
        pos = start + match.start()
        line = body.count("\n", 0, pos) + 1
        end = segment.find(";", match.end())
        excerpt = segment[match.start():end + 1 if end >= 0 else match.end()].strip()[:500]
        raw_args = segment[match.end():end if end >= 0 else match.end()].strip()
        required = match.group(1) == "addRequiredParam"
        # A sole quoted argument after the name is a description, not a default.
        has_default = not required and raw_args.lstrip(", ").strip()[:1] != '"'
        enum_literal = (re.search(r'MooseEnum\s*\(\s*"([^"]+)"', raw_args)
                        if "MooseEnum" in match.group(2) else None)
        params.append({
            "name": match.group(3), "cpp_type": " ".join(match.group(2).split()),
            "allowed_enum_values": (
                enum_literal.group(1).split() if enum_literal else None),
            "declaration": match.group(1), "required": required,
            "has_explicit_source_default": has_default,
            "declared_default_expression": raw_args[:240] if has_default else None,
            "raw_arguments_after_name": raw_args[:300],
            "runtime_effective_value": "NOT_OBSERVED",
            "witness": {"path": path, "line": line, "blob_sha": blob, "excerpt": excerpt}
        })
    for match in PARAM_SET.finditer(segment):
        line = body.count("\n", 0, start + match.start()) + 1
        params.append({
            "name": match.group(2), "cpp_type": " ".join(match.group(1).split()),
            "declaration": "set_default", "required": False,
            "has_explicit_source_default": True,
            "raw_arguments_after_name": match.group(3).strip(),
            "declared_default_expression": match.group(3).strip(),
            "runtime_effective_value": "NOT_OBSERVED",
            "witness": {"path": path, "line": line, "blob_sha": blob,
                        "excerpt": match.group(0).strip()[:500]}
        })
    return sorted(params, key=lambda p: (p["name"], p["witness"]["line"]))


def validate_declared_instance(instance: dict | None, parameters: list[dict]) -> dict:
    """Source-only local-parameter check, never proof of generated/native input."""
    if instance is None:
        return {"status": "UNKNOWN", "mode": "UNKNOWN",
                "unresolved": ["INSTANCE_NOT_SOURCE_BOUND"], "invalid": []}
    params = {p["name"]: p for p in parameters}
    bindings = {b["name"]: b for b in instance["bindings"]}
    invalid = []
    unresolved = []
    for name, param in sorted(params.items()):
        if param["required"] and name not in bindings:
            # Includes and dynamic overrides may provide it at runtime.
            # Missing from a source *template* is an OPEN proof gap, not
            # evidence of a successfully constructed invalid native object.
            unresolved.append("REQUIRED_LOCAL_PARAM_EFFECTIVE_BINDING_UNKNOWN:" + name)
    mode = bindings.get("state_form")
    mode_status = "UNKNOWN"
    if mode is not None:
        declared = mode["raw_value"].strip("'\"")
        enum = params.get("state_form")
        if enum and enum.get("allowed_enum_values"):
            mode_status = ("SUPPORTED_SOURCE_DECLARATION"
                           if declared in enum["allowed_enum_values"]
                           else "INVALID_DECLARED_MODE")
            if mode_status == "INVALID_DECLARED_MODE":
                invalid.append({
                    "name": "state_form", "reason": "INVALID_DECLARED_MODE",
                    "declared_value": declared,
                    "allowed_values": enum["allowed_enum_values"],
                    "source_witness": enum["witness"],
                    "input_witness": {"path": instance["input_path"],
                                      "line": mode["line"],
                                      "blob_sha": instance["evidence"]["blob_sha"]}})
        else:
            unresolved.append("STATE_FORM_ENUM_NOT_LOCALLY_PROVEN")
    elif "state_form" in params:
        mode_status = "UNKNOWN_DEFAULT_OR_INHERITED"
    if instance.get("instance_kind") == "PYTHON_GENERATED_INPUT_TEMPLATE_NOT_EXECUTED":
        unresolved.append("GENERATED_INPUT_NOT_OBSERVED")
    return {
        "status": "INVALID" if invalid else "UNKNOWN" if unresolved
                 else "SUPPORTED_SOURCE_ONLY",
        "mode": mode_status,
        "invalid": invalid, "unresolved": unresolved,
        "runtime_status": "NOT_OBSERVED",
        "representation": "NOT_PROVEN_FOR_EFFECTIVE_INPUT",
        "units": "NOT_PROVEN_FOR_EFFECTIVE_INPUT",
        "support": "LOCAL_VALIDPARAMS_AND_DECLARED_INPUT_ONLY_NOT_CHECK_INPUT"
    }


def shared_unit_evidence(root: Path, profile: dict) -> dict | None:
    """Bind all Factory registrations in a shared C++ translation unit."""
    unit = profile.get("shared_translation_unit")
    if unit is None:
        return None
    path = unit.get("source_path")
    expected = unit.get("co_registered_classes")
    if (path != profile["source"]["path"] or not isinstance(expected, list)
            or len(expected) < 2 or len(set(expected)) != len(expected)
            or profile["target"] not in expected):
        raise ValueError("SHARED_TRANSLATION_UNIT_CONTRACT_MALFORMED")
    data = safe_path(root, path).read_bytes()
    sha = structural.blob_sha(data)
    if sha != profile["source"]["blob_sha"]:
        raise ValueError("STALE_SHARED_TRANSLATION_UNIT_SOURCE")
    body = data.decode("utf-8")
    found = {}
    for match in structural.REGISTRATION.finditer(body):
        cls = match.group(3)
        found.setdefault(cls, []).append({
            "path": path, "blob_sha": sha,
            "line_start": body.count("\n", 0, match.start()) + 1,
            "excerpt": match.group(0)})
    if set(found) != set(expected):
        raise ValueError("SHARED_TRANSLATION_UNIT_OWNER_SET_CHANGED")
    return {
        "source_path": path, "blob_sha": sha,
        "co_registered_classes": sorted(expected),
        "registrations": found,
        "retirement_constraint": unit["retirement_constraint"],
        "status": "GROUP_REGISTERED_NOT_RETIRED"
    }


def validate_candidate_source(root: Path, candidate: dict) -> list[dict]:
    """Optional candidate source observation, NOT a replacement-equivalence claim."""
    contract = candidate.get("comparison_contract")
    if not isinstance(contract, dict) or contract.get("status") != "CANDIDATE_UNVERIFIED":
        raise ValueError("FUNCTIONAL_REPLACEMENT_DIFF_NOT_UNVERIFIED")
    if contract.get("decision") != "HOLD" or contract.get("runtime_evidence") != "NOT_OBSERVED":
        raise ValueError("FUNCTIONAL_REPLACEMENT_DIFF_FALSE_PROMOTION")
    dimensions = contract.get("dimensions")
    mandatory = {"representation", "residual_formula", "sign", "units", "time_state",
                 "face_and_boundary", "interpolation_and_limiter", "ad_jacobian",
                 "parameters_and_defaults", "source_owner"}
    if not isinstance(dimensions, dict) or set(dimensions) != mandatory:
        raise ValueError("FUNCTIONAL_REPLACEMENT_DIMENSIONS_INCOMPLETE")
    if any(spec.get("parity_status") != "NOT_EVALUATED" for spec in dimensions.values()):
        raise ValueError("FUNCTIONAL_REPLACEMENT_DIMENSION_FALSE_PASS")
    source = contract.get("candidate_source", {})
    if "path" not in source:
        if source.get("source_status") != "NOT_LOCALLY_SOURCE_VERIFIED":
            raise ValueError("FUNCTIONAL_CANDIDATE_SOURCE_UNRESOLVED_CONTRACT")
        return []
    try:
        body = safe_path(root, source["path"]).read_bytes()
        text = body.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("FUNCTIONAL_CANDIDATE_SOURCE_UNREADABLE") from exc
    blob = structural.blob_sha(body)
    if blob != source.get("blob_sha"):
        raise ValueError("FUNCTIONAL_CANDIDATE_SOURCE_BLOB_CHANGED")
    a, b = (0, len(text))
    if source.get("function_scope"):
        a, b = function_span(text, source["function_scope"])
    witnesses = []
    for anchor in source.get("anchors", []):
        idx = text.find(anchor, a, b)
        if idx < 0 or idx + len(anchor) > b:
            raise ValueError("FUNCTIONAL_CANDIDATE_ANCHOR_MISSING")
        witnesses.append({"path": source["path"], "blob_sha": blob,
                          "line_start": text.count("\n", 0, idx) + 1,
                          "excerpt": anchor[:240],
                          "support": "CANDIDATE_SOURCE_EXPRESSION_NOT_EQUIVALENCE"})
    if not witnesses:
        raise ValueError("FUNCTIONAL_CANDIDATE_ANCHORS_MISSING")
    return witnesses


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
        if (candidate.get("comparison_contract", {}).get("decision") != "HOLD"
                or candidate["comparison_contract"].get("status") != "CANDIDATE_UNVERIFIED"):
            raise ValueError("FUNCTIONAL_ALTERNATIVE_DIFF_MISSING_OR_PROMOTED")
    preservation = profile.get("preservation_contract")
    if (not isinstance(preservation, dict)
            or preservation.get("applicability") != "IF_ACTIVATED_ONLY"
            or preservation.get("effective_runtime_status") != "UNKNOWN"
            or preservation.get("science_acceptance") != "NOT_EVALUATED"
            or not preservation.get("removal_effect")):
        raise ValueError("FUNCTIONAL_PRESERVATION_CONTRACT_MISSING")


def consumer_role(edge: dict) -> str | None:
    relationship = edge["relation"]
    return {
        "INPUT_INSTANTIATES": "DECLARED_INPUT_NOT_RUNTIME",
        "PYTHON_TEMPLATE_INSTANTIATES": "DECLARED_PYTHON_TEMPLATE_NOT_GENERATED_OR_RUNTIME",
        "INPUT_MATCHES_ACTION_SYNTAX": "DECLARED_ACTION_INPUT_NOT_RUNTIME",
        "ACTION_CREATES": "SOURCE_ACTION_FACTORY_CALL_NOT_RUNTIME",
        "ACTION_CREATES_VIA_LOCAL_LITERAL": "SOURCE_LEXICAL_FLOW_CANDIDATE",
        "CPP_CONSTRUCTS": "SOURCE_CPP_CONSTRUCTION_NOT_RUNTIME",
        "PYTHON_DECLARES_TYPE": "SOURCE_GENERATOR_DECLARATION_NOT_RUNTIME",
        "JSON_DECLARES_TYPE": "SOURCE_JSON_TYPE_NOT_RUNTIME",
        "MENTIONS_SYMBOL": "LEXICAL_MENTION_NOT_CONSUMER",
        "GENERATOR_EMITS_OBJECT_CANDIDATE": "STATIC_GENERATOR_TYPE_ROUTE_NOT_RUNTIME",
    }.get(relationship)


def assemble(root: Path, structural_report: dict, target: str, registry: dict,
             expected_head: str | None = None) -> dict:
    root = root.resolve()
    verify_structural(root, structural_report, target, expected_head)
    if registry.get("schema") != "fdeg.functional_registry.v0.2":
        raise ValueError("FUNCTIONAL_REGISTRY_SCHEMA")
    profile = registry.get("profiles", {}).get(target)
    if not isinstance(profile, dict) or profile.get("target") != target:
        raise ValueError("FUNCTIONAL_PROFILE_NOT_AVAILABLE:" + target)
    validate_registry_profile(profile)
    witnesses, blobs = source_witnesses(root, profile)
    parameters = extract_parameters(root, profile)
    shared_unit = shared_unit_evidence(root, profile)
    preservation = profile["preservation_contract"]
    structural_enrichment = structural_report["enrichment"]
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
    semantic_diffs = []
    for candidate in profile.get("alternatives", []):
        candidate_witnesses = validate_candidate_source(root, candidate)
        diff = candidate["comparison_contract"]
        edge = {
            "claim_id": "candidate:" + target + ":" + candidate["candidate_type"],
            "from": "class:" + target, "relation": "ALTERNATIVE_CANDIDATE",
            "to": "class:" + candidate["candidate_type"],
            "conditions": candidate.get("conditions", []),
            "counterexamples": candidate.get("semantic_risks", []),
            "required_proof": candidate.get("requires", "INDEPENDENT_PARITY_PROOF"),
            "semantic_diff": diff,
            "evidence_kind": "REVIEW_REQUIREMENT_NOT_SOURCE_EQUIVALENCE",
            "claim_status": "CANDIDATE_UNVERIFIED",
            "runtime_status": "NOT_OBSERVED", "witnesses": candidate_witnesses
        }
        edge["edge_id"] = structural.stable_id("functional-edge", edge)
        functional_edges.append(edge)
        semantic_diffs.append({
            "candidate_type": candidate["candidate_type"], "functional_edge_id": edge["edge_id"],
            "comparison_contract": diff, "candidate_source_witnesses": candidate_witnesses,
            "equivalence_verdict": "NOT_PROVEN", "transition_permission": "HOLD"})
    if shared_unit is not None:
        for other in shared_unit["co_registered_classes"]:
            if other == target:
                continue
            edge = {
                "claim_id": "shared-file:" + target + ":" + other,
                "from": "class:" + target,
                "relation": "SHARES_TRANSLATION_UNIT_WITH",
                "to": "class:" + other,
                "shared_source_path": shared_unit["source_path"],
                "retirement_constraint": shared_unit["retirement_constraint"],
                "evidence_kind": "STATIC_SOURCE",
                "claim_status": "SOURCE_SUPPORTED",
                "runtime_status": "NOT_OBSERVED",
                "witnesses": shared_unit["registrations"][other]
            }
            edge["edge_id"] = structural.stable_id("functional-edge", edge)
            functional_edges.append(edge)
    for param in parameters:
        edge = {
            "claim_id": "param:" + target + ":" + param["name"],
            "from": "class:" + target, "relation": "DECLARES_PARAMETER",
            "to": "parameter:" + param["name"],
            "cpp_type": param["cpp_type"], "required": param["required"],
            "declaration": param["declaration"],
            "declared_default_expression": param["declared_default_expression"],
            "has_explicit_source_default": param["has_explicit_source_default"],
            "runtime_effective_value": "NOT_OBSERVED",
            "evidence_kind": "STATIC_SOURCE", "claim_status": "SOURCE_SUPPORTED",
            "witnesses": [param["witness"]]
        }
        edge["edge_id"] = structural.stable_id("functional-edge", edge)
        functional_edges.append(edge)
    functional_edges.sort(key=lambda e: (e["relation"], e["to"], e["claim_id"]))

    discriminators = profile.get("discriminator_contracts", {})
    required = set(profile.get("required_discriminators", []))
    if not isinstance(discriminators, dict) or set(discriminators) != required:
        raise ValueError("FUNCTIONAL_DISCRIMINATOR_CONTRACT_INCOMPLETE")
    for name, spec in discriminators.items():
        if (not isinstance(spec, dict) or not spec.get("setup")
                or not spec.get("observable") or not spec.get("expected")
                or spec.get("status") != "NOT_EVALUATED"):
            raise ValueError("FUNCTIONAL_DISCRIMINATOR_CANNOT_ASSERT_PASS:" + name)

    provider_map: dict[str, list[dict]] = {}
    for item in structural_enrichment["provider_bindings"]:
        provider_map.setdefault(item["instance_id"], []).append(item)
    params_by_name = {p["name"]: p for p in parameters}

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
            "instance_kind": instance.get("instance_kind", "TRACKED_MOOSE_INPUT")
                if instance else "NO_INSTANCE",
            "generated_output_path": instance.get("generated_output_path", "NOT_APPLICABLE")
                if instance else "UNKNOWN",
            "declared_bindings": instance["bindings"] if instance else [],
            "declared_input_validation": validate_declared_instance(instance, parameters),
            "input_path": instance["input_path"] if instance else edge["evidence"]["path"],
            "block_path": instance["block_path"] if instance else None,
            "declared_mode": next(
                (item["raw_value"] for item in instance["bindings"]
                 if item["name"] == "state_form"), "NOT_EXPLICITLY_SET")
                if instance else "UNKNOWN",
            "source_default_mode": (params_by_name["state_form"]["declared_default_expression"]
                                    if "state_form" in params_by_name else "NOT_DECLARED_LOCALLY"),
            "effective_runtime_binding": "UNKNOWN",
            "consumer_activation": "NOT_OBSERVED",
            "provider_bindings": provider_map.get(instance["instance_id"], []) if instance else [],
            "effective_functor_providers": "UNKNOWN",
            "effective_time_integrator": "UNKNOWN",
            "effective_state_and_face": "UNKNOWN",
            "equation_term_owner": (preservation["equation_term_owner"]
                                    if role != "LEXICAL_MENTION_NOT_CONSUMER" else "NOT_ESTABLISHED"),
            "functional_effect_if_removed": (preservation["removal_effect"]
                                             if role != "LEXICAL_MENTION_NOT_CONSUMER" else None),
            "applies_only_if_active": True,
            "obligations": sorted(preservation["coupled_guards"] + preservation["explicit_refusals"]),
            "required_discriminators": sorted(profile.get("required_discriminators", [])),
            "behavior_to_preserve": profile["capability"] if role != "LEXICAL_MENTION_NOT_CONSUMER" else None
        })
    consumers.sort(key=lambda c: (c["source_node"], c["structural_edge_id"]))
    # Explicit per-input functional ownership; no promotion to executed equation.
    for consumer in consumers:
        if not consumer["instance_id"]:
            continue
        edge = {
            "claim_id": "instance-owner:" + target + ":" + consumer["instance_id"],
            "from": consumer["instance_id"],
            "relation": "EQUATION_TERM_OWNER_CONDITIONAL",
            "to": "equation:" + preservation["equation_term_owner"],
            "source_structural_edge_id": consumer["structural_edge_id"],
            "functional_claim_ids": preservation["claim_ids"],
            "effect_if_active_removed": preservation["removal_effect"],
            "mode": consumer["declared_mode"],
            "runtime_status": "NOT_OBSERVED",
            "claim_status": "DECLARED_INPUT_ONLY",
            "evidence_kind": "STRUCTURAL_INSTANCE_PLUS_SOURCE_CONTRACT",
            "witnesses": []
        }
        edge["edge_id"] = structural.stable_id("functional-edge", edge)
        functional_edges.append(edge)
        for binding in consumer["provider_bindings"]:
            relation = {
                "claim_id": "provider:" + target + ":" + consumer["instance_id"] +
                            ":" + binding["parameter"],
                "from": "functor:" + binding["declared_name"],
                "relation": "EFFECTIVE_FUNCTIONAL_BINDING_CANDIDATE",
                "to": consumer["instance_id"],
                "source_structural_edge_id": consumer["structural_edge_id"],
                "parameter": binding["parameter"],
                "candidate_producers": binding["candidate_producers"],
                "effective_provider": "UNKNOWN",
                "claim_status": "SOURCE_DECLARATION_ONLY",
                "runtime_status": "NOT_OBSERVED",
                "evidence_kind": "STRUCTURAL_PROVIDER_CANDIDATE_NOT_RUNTIME",
                "witnesses": [binding["evidence"]]
            }
            relation["edge_id"] = structural.stable_id("functional-edge", relation)
            functional_edges.append(relation)
    for name, spec in sorted(discriminators.items()):
        item = {
            "claim_id": "discriminator:" + target + ":" + name,
            "from": "class:" + target, "relation": "REQUIRED_DISCRIMINATOR",
            "to": "oracle:" + name,
            "setup": spec["setup"], "observable": spec["observable"],
            "expected": spec["expected"],
            "acceptance_tolerance": spec.get("acceptance_tolerance", "OWNER_UNSPECIFIED"),
            "claim_status": "NOT_EVALUATED", "runtime_status": "NOT_OBSERVED",
            "evidence_kind": "REVIEWED_TEST_REQUIREMENT",
            "witnesses": []
        }
        item["edge_id"] = structural.stable_id("functional-edge", item)
        functional_edges.append(item)
    functional_edges.sort(key=lambda e: (e["relation"], e["to"], e["claim_id"]))

    unresolved = sorted(set(profile.get("unresolved_semantics", [])) |
                        ({"STRUCTURAL_TARGET_DEPENDENCIES_INCOMPLETE"}
                         if structural_report.get("target_dependency_status",
                                                  structural_report["status"]) == "INCOMPLETE"
                         else set()) |
                        ({"STRUCTURAL_UPSTREAM_GENERATOR_OR_INPUT_UNRESOLVED"}
                         if structural_report.get("upstream_unresolved") else set()))
    report = {
        "schema": SCHEMA, "target": target,
        "global_scan_status": structural_report["status"],
        "target_dependency_status": structural_report.get("target_dependency_status",
                                                          structural_report["status"]),
        "global_unresolved_count": structural_report.get("global_unresolved_count",
                                                         len(structural_report["unresolved"])),
        "source_identity": {
            "repository_head": structural_report["repository_head"],
            "structural_schema": structural_report["schema"],
            "structural_graph_id": structural_report["graph_id"],
            "source_blobs": dict(sorted(blobs.items())),
            "registry_schema": registry["schema"]},
        "capability": profile["capability"], "equation": profile["equation"],
        "operator_kind": profile["operator_kind"], "notes": profile.get("notes", ""),
        "edges": functional_edges,
        "nodes": [
            {"id": ident, "kind": "CLASS" if ident.startswith("class:")
             else "INSTANCE" if ident.startswith("instance:")
             else "FUNCTOR" if ident.startswith("functor:")
             else "EQUATION" if ident.startswith("equation:")
             else "ORACLE" if ident.startswith("oracle:")
             else "CAPABILITY" if ident.startswith("capability:")
             else "CONTRACT"}
            for ident in sorted({target_id for edge in functional_edges
                                 for target_id in (edge["from"], edge["to"])})
        ],
        "shared_translation_unit": shared_unit,
        "shared_file_retirement_requirement": (
            "ALL_REGISTERED_CLASSES_MUST_BE_DISCONNECTED"
            if shared_unit else "SINGLE_CLASS_SOURCE_PENDING_VERIFICATION"),
        "preservation_contract": preservation,
        "consumer_contracts": consumers,
        "semantic_replacement_diffs": semantic_diffs,
        "producer_binding_graph": structural_enrichment["provider_bindings"],
        "generator_consumer_routes": structural_enrichment["generator_routes"],
        "build_and_header_ownership": {
            "build": structural_enrichment["build_ownership"],
            "translation_units": structural_enrichment["shared_translation_units"]},
        "workflow_execution_routes": structural_enrichment["workflow_execution_paths"],
        "external_generator_imports": structural_enrichment["external_imports"],
        "target_scoped_unresolved": structural_report["target_scoped_unresolved"],
        "upstream_unresolved": structural_report.get("upstream_unresolved", []),
        "source_template_census": structural_report.get("source_template_census"),
        "required_discriminators": sorted(profile.get("required_discriminators", [])),
        "discriminator_contracts": {key: discriminators[key] for key in sorted(discriminators)},
        "parameter_declarations": parameters,
        "discriminator_evidence_status": "NOT_EVALUATED",
        "historical_guards": sorted(profile.get("historical_guards", [])),
        "unresolved_obligations": unresolved,
        "consumer_binding_verdict": "DECLARED_ONLY_EFFECTIVE_UNKNOWN",
        "replacement_verdict": "ALL_CANDIDATES_UNVERIFIED",
        "discriminator_verdict": "NOT_EVALUATED",
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
