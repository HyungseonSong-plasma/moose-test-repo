#!/usr/bin/env python3
"""FDEG Transition Evidence v0.1: conditional, source-bound migration planning data.

No mutation, runtime proof, substitution decision, caller-zero, or SAFE_DELETE.
The deterministic module describes constraints; GPT/human reviewers author plans.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fdeg_structural as structural  # noqa: E402
import fdeg_functional as functional  # noqa: E402

SCHEMA = "fdeg.transition.v0.1"
POLICY_SCHEMA = "fdeg.transition_policy.v0.1"
POLICY_PATH = Path("ci/baselines/fdeg_transition_contracts.json")
EXPECTED_STRATEGIES = {
    "RETAIN_NO_APPROVED_REPLACEMENT",
    "REWIRE_ONLY_IF_PARITY_PROVEN",
    "RETAIN_OR_CONDITIONALLY_REWIRE",
    "SHARED_FILE_INDEPENDENT_OWNER_GATES",
}
STEP_ORDER = (
    "PIN_EVIDENCE", "RESOLVE_CONSUMER_SCOPE", "QUALIFY_REPLACEMENT",
    "REWIRE_DECLARED_CONSUMERS", "VERIFY_FUNCTION_AND_HISTORY",
    "REBUILD_AND_COMPARE_GRAPHS", "REVIEW_SOURCE_RETIREMENT",
    "VERIFY_POST_CHANGE_AND_ROLLBACK",
)


def load_policy(root: Path, path: Path = POLICY_PATH) -> tuple[dict, str]:
    raw = functional.safe_path(root.resolve(), path.as_posix()).read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc, dict) or doc.get("schema") != POLICY_SCHEMA:
        raise ValueError("TRANSITION_POLICY_SCHEMA")
    return doc, structural.blob_sha(raw)


def policy_for(policy: dict, target: str) -> dict:
    if policy.get("schema") != POLICY_SCHEMA:
        raise ValueError("TRANSITION_POLICY_SCHEMA")
    safety = policy.get("controls", {})
    if safety.get("safety") != "SAFE_DELETE_ALWAYS_HOLD":
        raise ValueError("TRANSITION_POLICY_UNSAFE_GLOBAL_CONTROL")
    profile = policy.get("profiles", {}).get(target)
    if not isinstance(profile, dict) or profile.get("target") != target:
        raise ValueError("TRANSITION_POLICY_TARGET_MISSING:" + target)
    if (profile.get("status") != "REVIEWED_REQUIREMENTS_NOT_VERIFIED_EXECUTION"
            or profile.get("strategy") not in EXPECTED_STRATEGIES
            or not profile.get("review_url")
            or not profile.get("required")
            or not isinstance(profile.get("protected"), list)
            or not isinstance(profile.get("historical"), list)):
        raise ValueError("TRANSITION_POLICY_PROFILE_INVALID")
    if profile.get("shared_owner_group") and profile["strategy"] != "SHARED_FILE_INDEPENDENT_OWNER_GATES":
        raise ValueError("TRANSITION_SHARED_OWNER_STRATEGY_MISMATCH")
    return profile


def verify_inputs(root: Path, structural_report: dict, functional_report: dict,
                  target: str, expected_head: str | None = None) -> dict:
    """Read-back independently regenerated Functional, including Structural witness checks."""
    if structural_report.get("schema") != structural.SCHEMA or structural_report.get("target") != target:
        raise ValueError("TRANSITION_STRUCTURAL_SCHEMA_OR_TARGET_MISMATCH")
    if functional_report.get("schema") != functional.SCHEMA or functional_report.get("target") != target:
        raise ValueError("TRANSITION_FUNCTIONAL_SCHEMA_OR_TARGET_MISMATCH")
    src = functional_report.get("source_identity", {})
    if (src.get("structural_graph_id") != structural_report.get("graph_id")
            or src.get("repository_head") != structural_report.get("repository_head")):
        raise ValueError("TRANSITION_CROSS_GRAPH_IDENTITY_MISMATCH")
    body = {k: v for k, v in functional_report.items() if k != "graph_id"}
    if structural.stable_id("functional-graph", body) != functional_report.get("graph_id"):
        raise ValueError("TRANSITION_FUNCTIONAL_GRAPH_ID_INVALID")
    for edge in functional_report.get("edges", []):
        payload = {k: v for k, v in edge.items() if k != "edge_id"}
        if edge.get("edge_id") != structural.stable_id("functional-edge", payload):
            raise ValueError("TRANSITION_FUNCTIONAL_EDGE_ID_INVALID")
    registry = functional.load_registry(root)
    regenerated = functional.assemble(root, structural_report, target, registry, expected_head)
    if regenerated["graph_id"] != functional_report["graph_id"]:
        raise ValueError("TRANSITION_FUNCTIONAL_SOURCE_RECONSTRUCTION_MISMATCH")
    if (functional_report.get("runtime_observation") != "NOT_OBSERVED"
            or functional_report.get("equivalence_verdict") != "NOT_PROVEN"
            or functional_report.get("replacement_verdict") != "ALL_CANDIDATES_UNVERIFIED"
            or functional_report.get("discriminator_verdict") != "NOT_EVALUATED"):
        raise ValueError("TRANSITION_UNVERIFIED_ASSERTED_AS_PASS")
    return regenerated


def obligation(kind: str, target: str, consumer: str | None, description: str,
               gate: str, oracle: str, origin: str, owner: str = "DOMAIN_OWNER") -> dict:
    record = {
        "object": "class:" + target, "consumer": consumer,
        "kind": kind, "required_evidence": description,
        "gate": gate, "oracle": oracle,
        "owner": owner, "status": "OPEN", "origin_ref": origin,
    }
    record["obligation_id"] = structural.stable_id("blocking-obligation", record)
    return record


def edge(frm: str, relation: str, to: str, detail: dict) -> dict:
    item = {"from": frm, "relation": relation, "to": to, **detail}
    item["edge_id"] = structural.stable_id("transition-edge", item)
    return item


def compose(structural_report: dict, functional_report: dict, policy: dict,
            policy_blob: str = "UNVERIFIED_IN_MEMORY") -> dict:
    """Pure graph composition; public assemble() performs source-level verification first."""
    target = functional_report["target"]
    profile = policy_for(policy, target)
    if structural_report["target"] != target:
        raise ValueError("TRANSITION_COMPOSE_TARGET_MISMATCH")
    if (functional_report["source_identity"]["structural_graph_id"] != structural_report["graph_id"]
            or functional_report["source_identity"]["repository_head"] != structural_report["repository_head"]):
        raise ValueError("TRANSITION_COMPOSE_GRAPH_MISMATCH")
    head = structural_report["repository_head"]
    if functional_report["graph_id"] is None:
        raise ValueError("TRANSITION_FUNCTIONAL_ID_MISSING")
    if structural_report.get("status") not in ("INCOMPLETE", "STRUCTURAL_RECORDED"):
        raise ValueError("TRANSITION_STRUCTURAL_STATUS_INVALID")
    if (functional_report.get("equivalence_verdict") != "NOT_PROVEN"
            or functional_report.get("runtime_observation") != "NOT_OBSERVED"
            or functional_report.get("replacement_verdict") != "ALL_CANDIDATES_UNVERIFIED"):
        raise ValueError("TRANSITION_INVALID_FUNCTIONAL_VERDICT")

    incident = "class:" + target
    edges = []
    blockers: list[dict] = []
    seen_blockers: set[str] = set()

    def add_block(kind: str, desc: str, gate: str = "COVERAGE_OR_NATIVE",
                  oracle: str = "INDEPENDENT_OBSERVATION_REQUIRED",
                  consumer: str | None = None, origin: str | None = None) -> str:
        b = obligation(kind, target, consumer, desc, gate, oracle,
                       origin or profile["review_url"])
        if b["obligation_id"] not in seen_blockers:
            blockers.append(b)
            seen_blockers.add(b["obligation_id"])
            edges.append(edge(consumer or incident, "BLOCKED_BY", b["obligation_id"],
                              {"status": "UNRESOLVED", "evidence_origin": b["origin_ref"]}))
        return b["obligation_id"]

    # Required checks exist as specifications only: no runtime or science acceptance.
    for name, detail in sorted(functional_report["discriminator_contracts"].items()):
        if detail.get("status") != "NOT_EVALUATED":
            raise ValueError("TRANSITION_DISCRIMINATOR_FALSE_PASS")
        add_block("DISCRIMINATOR_NOT_EVALUATED",
                  name + " — " + detail["observable"] + "; expected: " + detail["expected"],
                  "NATIVE_INDEPENDENT_ORACLE", "ORACLE:" + name)
    for name in profile["required"]:
        add_block("TARGET_SPECIAL_REQUIREMENT", name, "TARGET_CHARACTERIZATION")
    for name in profile["historical"]:
        add_block("HISTORICAL_OR_COMPAT_GATE", name, "HISTORICAL_SEPARATE")
    for name in functional_report.get("unresolved_obligations", []):
        add_block("FUNCTIONAL_UNRESOLVED", name, "FUNCTIONAL_OR_RUNTIME")
    for fact in structural_report.get("target_scoped_unresolved", []):
        add_block("STRUCTURAL_UNRESOLVED",
                  fact["reason"] + " at " + fact["path"] + ":" + str(fact["line"]),
                  "STRUCTURAL_RUNTIME_SCOPE", consumer=None,
                  origin=structural.stable_id("unresolved", fact))
    for fact in structural_report.get("upstream_unresolved", []):
        add_block("UPSTREAM_GENERATOR_OR_INPUT_UNRESOLVED",
                  fact["reason"] + " at " + fact["path"] + ":" + str(fact["line"]),
                  "UPSTREAM_GENERATOR_OR_INPUT_COVERAGE",
                  origin=structural.stable_id("upstream-unresolved", fact))
    if structural_report["status"] == "INCOMPLETE" or structural_report.get("scan_errors"):
        add_block("INCOMPLETE_SCANNER", "Structural global scan incomplete; cannot assert coverage",
                  "STRUCTURAL_SCOPE")
    for name in ("RUNTIME_ACTIVE_CONSUMERS_AND_EXTERNAL_CALLERS",
                 "EFFECTIVE_INPUT_GENERATOR_AND_FUNCTOR_BINDINGS",
                 "APPROVED_NUMERICAL_TOLERANCES_AND_INDEPENDENT_ORACLE",
                 "POST_CHANGE_COVERAGE_AND_CALLER_ZERO",
                 "EXPLICIT_DOMAIN_RETIREMENT_APPROVAL"):
        add_block("NON_STATIC_GAP", name)
    candidate_records = []
    functional_edge_ids = {e["edge_id"] for e in functional_report["edges"]}
    for item in functional_report["semantic_replacement_diffs"]:
        if item["functional_edge_id"] not in functional_edge_ids:
            raise ValueError("TRANSITION_CANDIDATE_EDGE_REFERENCE_INVALID")
        if (item.get("transition_permission") != "HOLD"
                or item.get("equivalence_verdict") != "NOT_PROVEN"
                or item["comparison_contract"].get("decision") != "HOLD"):
            raise ValueError("TRANSITION_CANDIDATE_FALSE_PROMOTION")
        candidate = {
            "candidate_type": item["candidate_type"],
            "functional_edge_id": item["functional_edge_id"],
            "comparison_contract": item["comparison_contract"],
            "source_witnesses": item["candidate_source_witnesses"],
            "source_is_verified_equivalence": False,
            "parameter_mapping_proposal": profile.get("candidate_bindings", {}).get(item["candidate_type"], {}),
            "status": "CANDIDATE_UNVERIFIED",
            "transition_permission": "HOLD",
        }
        candidate_records.append(candidate)
        edges.append(edge(incident, "REWIRES_TO", "class:" + item["candidate_type"], {
            "role": "UNVERIFIED_OPTION_NOT_APPLIED",
            "functional_edge_id": item["functional_edge_id"],
            "status": "CANDIDATE_UNVERIFIED",
        }))
        add_block("REPLACEMENT_PARITY_NOT_PROVEN", "Candidate " + item["candidate_type"] +
                  ": ten semantic dimensions and residual/AD parity unverified",
                  "NATIVE_RESIDUAL_AD_PARITY")
    if not candidate_records:
        add_block("NO_APPROVED_REPLACEMENT", "No reviewed candidate or approved replacement owner",
                  "OWNER_DECISION")
        add_block("COMPATIBILITY_TERMINATION_NOT_APPROVED",
                  "Direct retirement requires verified supported-scope absence, "
                  "independent coverage/caller-zero, preserved history and explicit "
                  "old-input current-binary compatibility termination approval",
                  "INDEPENDENT_COVERAGE_AND_OWNER_APPROVAL")

    struct_edges = {e["edge_id"]: e for e in structural_report["edges"]}
    instances = {i["instance_id"]: i for i in structural_report["instances"]}
    consumers = []
    proposed_removed = []
    for item in functional_report["consumer_contracts"]:
        sid = item["structural_edge_id"]
        if sid not in struct_edges:
            raise ValueError("TRANSITION_CONSUMER_EDGE_NOT_IN_STRUCTURAL")
        se = struct_edges[sid]
        if se["to"] != incident:
            raise ValueError("TRANSITION_CONSUMER_TARGET_NOT_MATCHED")
        iid = item.get("instance_id")
        if iid is not None and iid not in instances:
            raise ValueError("TRANSITION_CONSUMER_INSTANCE_NOT_IN_STRUCTURAL")
        role = item["role"]
        historical = se.get("revision_scope") == "HISTORICAL_SOURCE_NOT_PROVEN_ACTIVE"
        history_location_unknown = (
            se.get("revision_scope") == "HISTORICAL_LOCATION_ACTIVITY_UNKNOWN")
        lexical = role == "LEXICAL_MENTION_NOT_CONSUMER"
        declared_validation = item.get("declared_input_validation", {
            "status": "UNKNOWN", "mode": "UNKNOWN", "invalid": [],
            "unresolved": ["VALIDATION_NOT_AVAILABLE"]})
        if declared_validation.get("status") == "INVALID":
            add_block("INVALID_GENERATED_INPUT",
                      "Invalid declared/local generated template for "
                      + item["input_path"] + " "
                      + str(declared_validation.get("invalid", [])),
                      "SOURCE_INPUT_CONTRACT", consumer="consumer:" + sid)
        if history_location_unknown and not lexical:
            add_block("HISTORICAL_LOCATION_CURRENT_USE_UNRESOLVED",
                      "Source path looks historical but may be current generator/CI consumer",
                      "CURRENT_ENTRYPOINT_COMPATIBILITY", consumer="consumer:" + sid)
        disposition = ("PRESERVE_HISTORICAL" if historical else
                       "REFERENCE_ONLY" if lexical else "HOLD_UNKNOWN")
        proposal = ("PRESERVE_HISTORY" if historical else
                    "DO_NOT_REWIRE_LEXICAL_REFERENCE" if lexical else
                    "REWIRE_CANDIDATE_ONLY_AFTER_GATES" if candidate_records
                    else "RETAIN_UNTIL_APPROVED_OWNER")
        current = {
            "consumer_id": "consumer:" + sid,
            "structural_edge_id": sid, "instance_id": iid,
            "source_node": item["source_node"], "role": role,
            "evidence_strength": item["evidence_strength"],
            "reference_scope": se.get("revision_scope"),
            "source_role": se.get("source_role", "SOURCE_ROLE_UNKNOWN"),
            "input_path": item["input_path"], "block_path": item["block_path"],
            "instance_kind": item.get("instance_kind", "NO_INSTANCE"),
            "declared_input_validation": declared_validation,
            "disposition_options": (
                ["PRESERVE_FROZEN_SOURCE", "CURRENT_CONSUMER_MIGRATION_REQUIRED_OR_HOLD"]
                if history_location_unknown else
                ["PRESERVE_HISTORICAL", "CURRENT_BINARY_COMPATIBILITY_SEPARATE"]
                if historical else
                ["REFERENCE_ONLY"] if lexical else
                ["REWIRE_WITH_INDEPENDENT_PARITY", "RETAIN"]
                if candidate_records else
                ["RETAIN", "RETIRE_UNSUPPORTED_CONSUMER_WITH_EXPLICIT_APPROVAL"]),
            "direct_retirement_preconditions": (
                ["SUPPORTED_SCOPE_PROVEN_NO_ACTIVE_CONSUMERS",
                 "EXTERNAL_AND_GENERATED_CONSUMER_COVERAGE",
                 "CURRENT_BINARY_OLD_INPUT_COMPATIBILITY_TERMINATION_APPROVAL",
                 "HISTORICAL_RECEIPT_FROZEN",
                 "OWNER_ACCEPTANCE_AND_POST_CUT_NATIVE_CI"]
                if not candidate_records else []),
            "before": {"type": target, "bindings": item["declared_bindings"],
                       "declared_mode": item["declared_mode"],
                       "effective_provider": "UNKNOWN",
                       "runtime_activation": "NOT_OBSERVED"},
            "after_proposal": {"candidate_options": [c["candidate_type"] for c in candidate_records],
                               "binding_status": "NOT_SPECIFIED_UNTIL_REPLACEMENT_PROOF",
                               "expected_removed_structural_edge_id": sid if candidate_records and not lexical and not historical else None},
            "disposition": disposition,
            "disposition_proposal": proposal,
            "proposed_only": True,
            "affected_paths": (
                [item["input_path"]] if not historical and not lexical
                and candidate_records and not history_location_unknown else []),
            "protected_or_reference_paths": (
                [item["input_path"]] if historical or lexical
                or history_location_unknown else []),
            "function_to_preserve_if_active": None if lexical else item.get("functional_effect_if_removed"),
            "functional_claim_ids": ([] if lexical else functional_report["preservation_contract"]["claim_ids"]),
            "evidence_status": "STATIC_DECLARATION_NOT_EXECUTION",
            "execution_status": "NOT_EXECUTED",
        }
        if iid and candidate_records and not lexical and not historical:
            proposed_removed.append(sid)
        if not lexical and not historical:
            bid = add_block("CONSUMER_ACTIVATION_UNVERIFIED",
                            "Effective object activation and before/after bindings not attested",
                            "NATIVE_ACTIVATION_AND_BINDING", consumer=current["consumer_id"])
            current["blocking_obligation_ids"] = [bid]
        else:
            current["blocking_obligation_ids"] = []
        current["blocking_obligation_ids"] = sorted(set(
            current["blocking_obligation_ids"] +
            [b["obligation_id"] for b in blockers
             if b.get("consumer") == current["consumer_id"]]))
        consumers.append(current)
        edges.append(edge(incident, "HAS_DISPOSITION", current["consumer_id"], {
            "disposition": disposition, "status": "PLANNED_ONLY",
            "structural_edge_id": sid,
        }))
        for claim in current["functional_claim_ids"]:
            claim_id = "claim:" + target + ":" + claim
            matched = [x for x in functional_report["edges"] if x.get("claim_id") == claim_id]
            if not matched:
                raise ValueError("TRANSITION_MISSING_FUNCTIONAL_CLAIM:" + claim_id)
            edges.append(edge(current["consumer_id"], "PRESERVES", matched[0]["edge_id"], {
                "functional_claim_id": claim_id, "status": "PRESERVATION_REQUIRED_IF_ACTIVE"
            }))
    consumers.sort(key=lambda c: c["structural_edge_id"])
    if not consumers:
        add_block("NO_IDENTIFIED_CONSUMERS_IS_NOT_CALLER_ZERO",
                  "No target-rooted consumer observed by static scan; external/dynamic coverage unknown",
                  "COVERAGE_SCOPE")

    declared_sites = sorted(set(
        p for c in consumers for p in c["affected_paths"]))
    protected_or_reference_sites = sorted(set(
        p for c in consumers for p in c["protected_or_reference_paths"]))
    generators = functional_report.get("generator_consumer_routes", [])
    generator_sites = sorted({g["source"] for g in generators})
    generated_candidates = sorted({
        p for g in generators for p in g.get("output_candidates", [])
    })
    workflows = sorted({w["workflow_path"] for w in functional_report.get("workflow_execution_routes", [])})
    source_owners = sorted({
        x["source_path"] for x in functional_report["build_and_header_ownership"]["translation_units"]
    })
    protected = sorted(set(profile["protected"]))
    for resource in protected:
        edges.append(edge(incident, "PRESERVES", "protected:" + resource, {
            "status": "PRESERVE_INDEPENDENT_OWNER",
            "evidence": "REVIEWED_REQUIREMENT_NOT_RUNTIME"
        }))
    shared = functional_report.get("shared_translation_unit")
    if shared:
        registered = set(shared["co_registered_classes"])
        if target not in registered or len(registered) <= 1:
            raise ValueError("TRANSITION_SHARED_OWNER_SET_INVALID")
        if profile.get("shared_owner_group") is None:
            raise ValueError("TRANSITION_SHARED_POLICY_MISSING")
        for other in sorted(registered - {target}):
            add_block("SHARED_OWNER_MUST_BE_DISCHARGED",
                      "Shared translation unit owner " + other + " has not been independently retired",
                      "MULTI_CLASS_OWNER_COVERAGE")
    elif profile.get("shared_owner_group"):
        raise ValueError("TRANSITION_SHARED_TRANSLATION_UNIT_MISSING")

    # A readable sequential DAG with per-consumer change evidence is a proposal,
    # never a deterministic authorization to execute or to remove source files.
    scopes = {
        "PIN_EVIDENCE": [],
        "RESOLVE_CONSUMER_SCOPE": declared_sites + generator_sites + generated_candidates,
        "QUALIFY_REPLACEMENT": source_owners,
        "REWIRE_DECLARED_CONSUMERS": declared_sites,
        "VERIFY_FUNCTION_AND_HISTORY": declared_sites + generated_candidates,
        "REBUILD_AND_COMPARE_GRAPHS": declared_sites + generator_sites + workflows,
        "REVIEW_SOURCE_RETIREMENT": source_owners,
        "VERIFY_POST_CHANGE_AND_ROLLBACK": source_owners + declared_sites,
    }
    step_gate = {
        "PIN_EVIDENCE": ["EXACT_SHA_GRAPH_AND_BLOB_IDS"],
        "RESOLVE_CONSUMER_SCOPE": ["RUNTIME_INSTANCE_FUNCTOR_GENERATOR_EXTERNAL_COVERAGE"],
        "QUALIFY_REPLACEMENT": ["OWNER_SEMANTIC_DIFF_AND_APPROVED_NUMERICAL_ORACLE"],
        "REWIRE_DECLARED_CONSUMERS": ["P0_INPUT_GENERATOR_AND_GUARD_CONTRACTS"],
        "VERIFY_FUNCTION_AND_HISTORY": ["P1_BUILD", "P2_CHECK_INPUT", "P3_INDEPENDENT_RESIDUAL_AD",
                                        "HISTORICAL_REPLAY_SEPARATE"],
        "REBUILD_AND_COMPARE_GRAPHS": ["POST_CHANGE_SOURCE_GRAPH_DIFF_NO_MISSING_OR_DOUBLE_TERM"],
        "REVIEW_SOURCE_RETIREMENT": ["ALL_OWNERS_DISCONNECTED", "COVERAGE_SEPARATE_APPROVAL"],
        "VERIFY_POST_CHANGE_AND_ROLLBACK": ["EXACT_HEAD_REPOSITORY_CI", "NATIVE_POST_CHANGE_REVALIDATION"],
    }
    steps = []
    consumer_step_ids = []
    history_step_ids = []
    for index, name in enumerate(STEP_ORDER):
        # Insert per-consumer candidate work AFTER qualification, BEFORE the
        # aggregate rewire gate, so exact instance/edge edits are not lost.
        if name == "REWIRE_DECLARED_CONSUMERS":
            for consumer in consumers:
                if consumer["disposition"] not in {"HOLD_UNKNOWN", "PRESERVE_HISTORICAL"}:
                    continue
                is_history = consumer["disposition"] == "PRESERVE_HISTORICAL"
                verb = ("PRESERVE_HISTORICAL_CONSUMER" if is_history else
                        "REWIRE_CONSUMER_CANDIDATE" if candidate_records else
                        "RETAIN_CONSUMER_UNTIL_APPROVAL")
                task_id = "step:" + verb + ":" + consumer["structural_edge_id"]
                parents = (["step:RESOLVE_CONSUMER_SCOPE"] if is_history else
                           ["step:QUALIFY_REPLACEMENT"])
                paths = consumer["affected_paths"]
                gates = (["PINNED_HISTORICAL_REPLAY_SEPARATE",
                          "CURRENT_BINARY_COMPATIBILITY_INDEPENDENT"] if is_history else
                         ["APPROVED_REPLACEMENT_OR_EXPLICIT_REMOVAL_OWNER",
                          "CONSUMER_ACTIVATION_AND_EFFECTIVE_BINDING"] if not candidate_records else
                         ["CONSUMER_ACTIVATION_AND_EFFECTIVE_BINDING",
                          "APPROVED_REPLACEMENT_SEMANTIC_PARITY",
                          "DIRECT_INPUT_GENERATOR_AND_CHECKER_P0"])
                task = {
                    "step_id": task_id, "operation": verb,
                    "consumer_id": consumer["consumer_id"],
                    "structural_edge_id": consumer["structural_edge_id"],
                    "instance_id": consumer["instance_id"],
                    "depends_on_steps": parents,
                    "status": "PLANNED", "execution_status": "NOT_EXECUTED",
                    "eligible_to_execute": False,
                    "preconditions": ["PREDECESSOR_VERIFIED",
                                      "OWNER_APPROVED_DISPOSITION_AND_ORACLE"],
                    "affected_paths": paths,
                    "before": consumer["before"],
                    "after_proposal": consumer["after_proposal"],
                    "expected_graph_delta": {
                        "kind": "PROPOSED_NOT_MEASURED",
                        "may_remove_structural_edge_ids":
                            [] if is_history or not candidate_records else [consumer["structural_edge_id"]],
                        "preserve_functional_claim_ids": sorted(
                            functional_report["preservation_contract"]["claim_ids"]),
                        "observed_removed_edges": []},
                    "verification_gates": [
                        {"gate": g, "status": "NOT_EVALUATED",
                         "oracle": "INDEPENDENT_EVIDENCE_REQUIRED",
                         "tolerance": "OWNER_UNSPECIFIED", "artifact": "NOT_ATTACHED"}
                        for g in gates],
                    "blocking_obligation_ids": sorted(
                        set(consumer["blocking_obligation_ids"] +
                            [b["obligation_id"] for b in blockers
                             if b["consumer"] is None])),
                    "stop_condition": "ANY_REQUIRED_EVIDENCE_MISSING_OR_FAILURE",
                    "rollback": {
                        "baseline_head": head, "restore_paths": paths,
                        "rollback_status": "RECIPE_ONLY_NOT_EXECUTED",
                        "after_rollback_gate":
                            "REGENERATE_EXACT_HEAD_P0_P1_P2_AS_APPLICABLE"}
                }
                steps.append(task)
                if is_history:
                    history_step_ids.append(task_id)
                else:
                    consumer_step_ids.append(task_id)
                edges.append(edge(task_id, "PRESERVES" if is_history or not candidate_records else
                                  "REWIRE_STEP", consumer["consumer_id"],
                                  {"status": "PROPOSED_ONLY", "structural_edge_id":
                                   consumer["structural_edge_id"]}))
                for parent in parents:
                    edges.append(edge(task_id, "DEPENDS_ON_STEP", parent,
                                      {"status": "ORDERING_CONSTRAINT_ONLY"}))
                for gate in gates:
                    edges.append(edge(task_id, "REQUIRES_EVIDENCE", "gate:" + gate,
                                      {"status": "NOT_EVALUATED"}))
                edges.append(edge(task_id, "ROLLBACK_TO", "commit:" + str(head),
                                  {"status": "PROPOSED_RECOVERY_TARGET"}))
        before = ["step:" + STEP_ORDER[index - 1]] if index else []
        if name == "REWIRE_DECLARED_CONSUMERS" and consumer_step_ids:
            before = sorted(consumer_step_ids)
        if name == "VERIFY_FUNCTION_AND_HISTORY" and history_step_ids:
            before += sorted(history_step_ids)
        stage = {
            "step_id": "step:" + name, "operation": name,
            "depends_on_steps": before, "status": "PLANNED",
            "execution_status": "NOT_EXECUTED", "eligible_to_execute": False,
            "preconditions": (["EXACT_INPUT_GRAPH_IDENTITY"] if index == 0
                              else ["PREDECESSOR_VERIFIED", "REQUIRED_EVIDENCE_APPROVED"]),
            "affected_paths": sorted(set(scopes[name])),
            "expected_graph_delta": {
                "kind": "PROPOSED_NOT_MEASURED",
                "may_remove_structural_edge_ids": (
                    sorted(set(proposed_removed)) if name == "REWIRE_DECLARED_CONSUMERS" else []),
                "preserve_functional_claim_ids": sorted(functional_report["preservation_contract"]["claim_ids"]),
                "observed_removed_edges": []
            },
            "verification_gates": [
                {"gate": g, "status": "NOT_EVALUATED",
                 "oracle": "INDEPENDENT_EVIDENCE_REQUIRED",
                 "tolerance": "OWNER_UNSPECIFIED",
                 "artifact": "NOT_ATTACHED"} for g in step_gate[name]
            ],
            "blocking_obligation_ids": sorted(b["obligation_id"] for b in blockers),
            "stop_condition": "ANY_REQUIRED_EVIDENCE_MISSING_OR_FAILURE",
            "rollback": {
                "baseline_head": head,
                "restore_paths": sorted(set(scopes[name])),
                "rollback_status": "RECIPE_ONLY_NOT_EXECUTED",
                "after_rollback_gate": "REGENERATE_EXACT_HEAD_P0_P1_P2_AS_APPLICABLE",
            }
        }
        steps.append(stage)
        for parent in before:
            edges.append(edge(stage["step_id"], "DEPENDS_ON_STEP", parent,
                              {"status": "ORDERING_CONSTRAINT_ONLY"}))
        edges.append(edge(stage["step_id"], "ROLLBACK_TO", "commit:" + str(head),
                          {"status": "PROPOSED_RECOVERY_TARGET"}))
        for gate in step_gate[name]:
            edges.append(edge(stage["step_id"], "REQUIRES_EVIDENCE", "gate:" + gate,
                              {"status": "NOT_EVALUATED"}))
    for route in generators:
        if route.get("activation") != "NOT_OBSERVED":
            raise ValueError("TRANSITION_GENERATOR_FALSE_ACTIVATION")

    edges.sort(key=lambda e: (e["from"], e["relation"], e["to"], e["edge_id"]))
    blockers.sort(key=lambda b: b["obligation_id"])
    candidate_records.sort(key=lambda c: c["candidate_type"])
    nodes = [{"id": id_, "kind": (
        "STEP" if id_.startswith("step:") else
        "CONSUMER" if id_.startswith("consumer:") else
        "CLASS" if id_.startswith("class:") else
        "BLOCKER" if id_.startswith("blocking-obligation:") else
        "OTHER")}
        for id_ in sorted({v for e in edges for v in (e["from"], e["to"])})]
    report = {
        "schema": SCHEMA, "target": target,
        "source_identity": {
            "repository_head": head,
            "structural_graph_id": structural_report["graph_id"],
            "functional_graph_id": functional_report["graph_id"],
            "structural_schema": structural_report["schema"],
            "functional_schema": functional_report["schema"],
            "policy_schema": policy["schema"],
            "policy_blob_sha": policy_blob,
        },
        "target_strategy": profile["strategy"],
        "review_source": profile["review_url"],
        "strategy_assumption": profile["rule"],
        "consumer_dispositions": consumers,
        "candidate_rewiring_options": candidate_records,
        "change_sites": {
            "declared_input_and_other_consumer_paths": declared_sites,
            "protected_or_reference_no_edit_paths": protected_or_reference_sites,
            "generator_paths": generator_sites,
            "generated_output_candidates_not_observed": generated_candidates,
            "workflow_paths": workflows,
            "source_ownership_paths": source_owners,
        },
        "protected_resources": protected,
        "shared_owner_contract": shared,
        "shared_owner_aggregate_requirement": (
            {"source_path": shared["source_path"],
             "registered_classes": sorted(shared["co_registered_classes"]),
             "all_registered_owners_must_be_disconnected": True,
             "target_owner": target,
             "target_owner_status": "HOLD_UNKNOWN",
             "other_owner_verification": "NOT_INCLUDED_IN_THIS_TARGET_GRAPH",
             "required_external_manifest": "FOUR_S_F_T_REPORTS_SAME_EXACT_HEAD",
             "whole_file_safe_delete": "HOLD"}
            if shared else None),
        "historical_gates": profile["historical"],
        "blocking_obligations": blockers,
        "steps": steps,
        "nodes": nodes, "edges": edges,
        "plan_status": "CONDITIONAL_PLAN",
        "execution_status": "NOT_EXECUTED",
        "runtime_observation": "NOT_OBSERVED",
        "numerical_equivalence": "NOT_PROVEN",
        "caller_zero": "NOT_PROVEN",
        "safe_delete": "HOLD",
        "safety": "GRAPH_ONLY_PLAN_NOT_RETIREMENT_AUTHORIZATION"
    }
    report["graph_id"] = structural.stable_id("transition-graph", report)
    return report


def assemble(root: Path, structural_report: dict, functional_report: dict,
             target: str, policy: dict, policy_blob: str = "UNVERIFIED_IN_MEMORY",
             expected_head: str | None = None) -> dict:
    root = root.resolve()
    policy_for(policy, target)
    if expected_head is not None:
        raw = functional.safe_path(root, POLICY_PATH.as_posix()).read_bytes()
        if structural.blob_sha(raw) != policy_blob:
            raise ValueError("TRANSITION_POLICY_BLOB_MISMATCH")
        if json.loads(raw.decode("utf-8")) != policy:
            raise ValueError("TRANSITION_POLICY_CONTENT_MISMATCH")
    verify_inputs(root, structural_report, functional_report, target, expected_head)
    return compose(structural_report, functional_report, policy, policy_blob)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--structural", type=Path, required=True)
    parser.add_argument("--functional", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        s = json.loads(args.structural.read_text(encoding="utf-8"))
        f = json.loads(args.functional.read_text(encoding="utf-8"))
        policy, sha = load_policy(root)
        result = assemble(root, s, f, args.target, policy, sha, args.expected_head)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("FDEG_TRANSITION_P0=FAIL:" + str(exc))
        return 1
    rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
        print("FDEG_TRANSITION_REPORT=" + str(args.output))
    else:
        print(rendered, end="")
    print("FDEG_TRANSITION_P0=PASS")
    print("FDEG_TRANSITION_PLAN=CONDITIONAL")
    print("FDEG_RETIREMENT=HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
