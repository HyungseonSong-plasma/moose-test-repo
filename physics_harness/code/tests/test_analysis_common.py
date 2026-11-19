"""Domain-neutral impact/Claim/assessment/provenance diff acceptance tests."""

from dataclasses import replace

import pytest

from physics_harness.code.analysis import (
    analyze_impact, assess_finding, compare_graphs, propose_finding,
)
from physics_harness.code.graph import (
    Edge, Evidence, GraphSnapshot, Node, Scope,
)


def sample(*, revision="a" * 40, complete=True,
           runtime_source_sha=None):
    scope = Scope(
        id="scope:sample",
        repository="example/repo", revision=revision,
        completeness="COMPLETE" if complete else "PARTIAL",
        unresolved=() if complete else ("DYNAMIC_EXTERNAL_CONSUMER",),
    )
    evidence = (
        Evidence("ev:static", "STRUCTURAL", "src/a.py:1", "PYTHON_AST",
                 scope.id, observation_status="SOURCE_DECLARED"),
        Evidence(
            "ev:runtime", "RUNTIME", "https://example.invalid/runs/5",
            "GITHUB_ACTIONS_REST", scope.id,
            observation_status="RUNTIME_OBSERVED",
            attributes={"source_sha": runtime_source_sha or revision,
                        "run_id": 5, "attempt": 1,
                        "url": "https://example.invalid/runs/5"},
        ),
    )
    return GraphSnapshot(
        scope=scope,
        nodes=(
            Node("node:producer", "file", "producer",
                 evidence_ids=("ev:static",)),
            Node("node:consumer", "file", "consumer"),
            Node("node:target", "symbol", "target"),
        ),
        edges=(
            Edge("edge:prod", "node:producer", "node:target",
                 "USES", evidence_ids=("ev:static",)),
            Edge("edge:cons", "node:consumer", "node:target",
                 "USES", evidence_ids=("ev:runtime",)),
            Edge("edge:back", "node:target", "node:consumer",
                 "USES", evidence_ids=("ev:static",)),
        ),
        evidence=evidence,
    )


def test_reverse_impact_reuses_context_and_retains_cycles_and_shared_paths():
    graph = sample()
    result = analyze_impact(
        graph, ("node:target",), ("USES",), max_depth=5,
    )
    assert result.complete_within_scope
    assert result.visited_nodes == (
        "node:consumer", "node:producer", "node:target",
    )
    assert len(result.visited_edges) == 3
    assert any(o.status == "CYCLE_REF" for o in result.view.occurrences)
    assert not result.view.truncated
    repeat = analyze_impact(graph, ("node:target",), ("USES",))
    assert result.view == repeat.view


def test_impact_scope_budget_and_evidence_filter_stay_fail_closed():
    graph = sample()
    limited = analyze_impact(graph, ("node:target",), ("USES",),
                             max_depth=0)
    assert "CONTEXT_TRUNCATED" in limited.blockers
    assert not limited.complete_within_scope

    observed_only = analyze_impact(
        graph, ("node:target",), ("USES",),
        evidence_filter=("RUNTIME_OBSERVED",),
    )
    assert observed_only.visited_nodes == ("node:consumer", "node:target")

    incomplete = analyze_impact(
        sample(complete=False), ("node:target",), ("USES",),
    )
    assert not incomplete.complete_within_scope
    assert "DYNAMIC_EXTERNAL_CONSUMER" in incomplete.blockers


def test_findings_validate_exact_graph_subjects_and_evidence_refs():
    graph = sample()
    claim = propose_finding(
        graph, "POSSIBLE_UNNECESSARY_VALIDATION", ("node:target",),
        supports=("ev:static",), qualifies=("ev:runtime",),
        conditions={"needs_review": True},
    )
    assert claim.assessment_status == "NOT_EVALUATED"
    assert [ref.role for ref in claim.evidence_refs] == [
        "QUALIFIES", "SUPPORTS",
    ]
    with pytest.raises(ValueError, match="UNKNOWN_FINDING_SUBJECT"):
        propose_finding(graph, "X", ("missing",))
    with pytest.raises(ValueError, match="UNKNOWN_FINDING_EVIDENCE"):
        propose_finding(graph, "X", ("node:target",), supports=("not:here",))
    with pytest.raises(ValueError, match="duplicate claim evidence link"):
        propose_finding(
            graph, "X", ("node:target",),
            supports=("ev:static", "ev:static"),
        )


def test_conditionally_supported_finding_is_only_verification_candidate():
    graph = sample()
    claim = propose_finding(
        graph, "REFACTOR_CANDIDATE", ("node:target",),
        supports=("ev:static",),
    )
    result = assess_finding(
        graph, claim, required_evidence_kinds=("STRUCTURAL",),
        verification_obligations=("full_suite", "semantic_parity"),
    )
    assert result.disposition == "CANDIDATE_FOR_VERIFICATION"
    assert result.claim.assessment_status == "QUALIFIED"
    assert result.verification_obligations == ("full_suite", "semantic_parity")
    assert not result.actionable_without_verification


def test_missing_evidence_incomplete_scope_and_qualifiers_hold():
    graph = sample()
    claim = propose_finding(
        graph, "X", ("node:target",), supports=("ev:static",),
    )
    unspecified = assess_finding(graph, claim)
    assert unspecified.disposition == "HOLD"
    assert "REQUIRED_EVIDENCE_CONTRACT_MISSING" in unspecified.blockers

    missing_runtime = assess_finding(
        graph, claim, required_evidence_kinds=("STRUCTURAL", "RUNTIME"),
    )
    assert missing_runtime.disposition == "HOLD"
    assert "REQUIRED_EVIDENCE_MISSING:RUNTIME" in missing_runtime.blockers

    incomplete = sample(complete=False)
    assertion = propose_finding(
        incomplete, "X", ("node:target",), supports=("ev:static",),
    )
    incomplete_result = assess_finding(
        incomplete, assertion, required_evidence_kinds=("STRUCTURAL",),
    )
    assert incomplete_result.disposition == "HOLD"
    assert "DYNAMIC_EXTERNAL_CONSUMER" in incomplete_result.blockers

    qualified = propose_finding(
        graph, "X", ("node:target",),
        supports=("ev:static",), qualifies=("ev:runtime",),
    )
    assert assess_finding(
        graph, qualified, required_evidence_kinds=("STRUCTURAL",),
    ).disposition == "HOLD"


def test_refuting_and_cross_head_runtime_evidence_do_not_approve_change():
    graph = sample()
    contradicted = propose_finding(
        graph, "UNUSED", ("node:target",),
        supports=("ev:static",), refutes=("ev:runtime",),
    )
    outcome = assess_finding(
        graph, contradicted, required_evidence_kinds=("STRUCTURAL",),
    )
    assert outcome.disposition == "BLOCKED"
    assert outcome.claim.assessment_status == "REFUTED"
    assert "REFUTING_EVIDENCE" in outcome.blockers

    cross_head = sample(runtime_source_sha="b" * 40)
    claim = propose_finding(
        cross_head, "RUNTIME_ACTIVE", ("node:target",),
        supports=("ev:runtime",),
    )
    flagged = assess_finding(
        cross_head, claim, required_evidence_kinds=("RUNTIME",),
    )
    assert flagged.disposition == "HOLD"
    assert any(x.startswith("CROSS_HEAD_RUNTIME_EVIDENCE")
               for x in flagged.blockers)


def test_evidence_only_diff_is_not_a_semantic_change_or_safety_proof():
    first = sample()
    second = sample(revision="b" * 40)
    # Evidence-only updates should remain visible without changing logical
    # Node/Edge payload identity.
    second_evidence = tuple(replace(e, id=e.id + ":after") for e in second.evidence)
    second_nodes = tuple(replace(
        n, evidence_ids=tuple(x + ":after" for x in n.evidence_ids),
    ) for n in second.nodes)
    second_edges = tuple(replace(
        e, evidence_ids=tuple(x + ":after" for x in e.evidence_ids),
    ) for e in second.edges)
    second = GraphSnapshot(
        second.scope, second_nodes, second_edges, second_evidence,
    )
    result = compare_graphs(first, second)
    assert not result.added_nodes
    assert not result.removed_nodes
    assert not result.changed_nodes
    assert not result.changed_edges
    assert len(result.added_evidence) == 2
    assert len(result.removed_evidence) == 2
    assert not result.semantic_compatibility_proven


def test_before_after_diff_tracks_changed_payload_and_unresolved_regression():
    before = sample()
    after = sample(revision="b" * 40, complete=False)
    modified_nodes = tuple(
        replace(node, name="target_v2") if node.id == "node:target" else node
        for node in after.nodes
    )
    modified_edges = tuple(
        replace(edge, relation="USES_CANDIDATE") if edge.id == "edge:prod" else edge
        for edge in after.edges
    )
    after = GraphSnapshot(
        after.scope, modified_nodes, modified_edges, after.evidence,
    )
    diff = compare_graphs(before, after)
    assert diff.changed_nodes == ("node:target",)
    assert diff.changed_edges == ("edge:prod",)
    assert diff.coverage_changed
    assert diff.new_unresolved == ("DYNAMIC_EXTERNAL_CONSUMER",)
    assert not diff.semantic_compatibility_proven


def test_diff_rejects_cross_repository_sources():
    before = sample()
    after = sample(revision="b" * 40)
    other_scope = replace(after.scope, repository="elsewhere/repo")
    after = replace(after, scope=other_scope)
    with pytest.raises(ValueError, match="CROSS_REPOSITORY_GRAPH_DIFF"):
        compare_graphs(before, after)
