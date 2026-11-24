"""D2/D3 P0: deterministic assembly, conflict checks and unresolved targets."""

from dataclasses import replace

import pytest

from physics_harness.code.graph import Edge, Evidence, Node
from physics_harness.code.diagnostics import (
    FactBatch, FileCoverage, GraphAssembler, ScanRequest,
    UnresolvedTarget, graph_edge_id, scan_scope_id,
)
from physics_harness.code.diagnostics.receipt import create_receipt


def fixture():
    request = ScanRequest(
        repository="example/repo", revision="a" * 40,
        includes=("src/*.py",), collectors=("mock",),
    )
    scope = scan_scope_id(request)
    receipt = create_receipt(
        request, scope_id=scope,
        files=(FileCoverage("src/a.py", "b" * 40, "SCANNED",
                            collectors=("mock",)),),
        collector_versions=(("mock", "v1"),),
    )
    ev1 = Evidence("ev:1", "STRUCTURAL", "src/a.py:1", "TEST", scope)
    ev2 = Evidence("ev:2", "STRUCTURAL", "src/a.py:2", "TEST", scope)
    return request, scope, receipt, ev1, ev2


def test_assembler_is_order_invariant_and_unions_evidence():
    req, scope, receipt, ev1, ev2 = fixture()
    node1 = Node("node:a", "symbol", "A", evidence_ids=("ev:1",))
    node2 = Node("node:a", "symbol", "A", evidence_ids=("ev:2",))
    target = Node("node:b", "symbol", "B")
    edge1 = Edge(
        graph_edge_id("node:a", "node:b", "CALLS", "site1"),
        "node:a", "node:b", "CALLS", "site1", evidence_ids=("ev:1",),
    )
    edge2 = replace(edge1, evidence_ids=("ev:2",))
    batches = (
        FactBatch((node1, target), (edge1,), (ev1,)),
        FactBatch((node2,), (edge2,), (ev2,)),
    )
    assembler = GraphAssembler()
    first = assembler.assemble(req, batches, receipt)
    second = assembler.assemble(req, batches[::-1], receipt)
    assert first.graph == second.graph
    assert first.graph.nodes_by_id()["node:a"].evidence_ids == ("ev:1", "ev:2")
    assert first.graph.edges[0].evidence_ids == ("ev:1", "ev:2")
    assert first.graph.scope.completeness == "COMPLETE"


def test_same_identity_conflicting_node_or_evidence_rejected():
    req, scope, receipt, ev1, ev2 = fixture()
    good = Node("node:a", "symbol", "A", evidence_ids=("ev:1",))
    conflict = Node("node:a", "symbol", "DIFFERENT", evidence_ids=("ev:1",))
    with pytest.raises(ValueError, match="NODE_ID_CONFLICT"):
        GraphAssembler().assemble(
            req, (FactBatch((good,), evidence=(ev1,)),
                  FactBatch((conflict,))), receipt,
        )
    ev_conflict = replace(ev1, source_ref="src/a.py:DIFFERENT")
    with pytest.raises(ValueError, match="EVIDENCE_ID_CONFLICT"):
        GraphAssembler().assemble(
            req, (FactBatch(evidence=(ev1,)),
                  FactBatch(evidence=(ev_conflict,))), receipt,
        )


def test_assembler_rejects_unproven_edges_and_cross_scope_evidence():
    req, scope, receipt, ev1, ev2 = fixture()
    missing = Edge(graph_edge_id("node:a", "node:b", "CALLS"), "node:a", "node:b", "CALLS")
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_REQUIRED"):
        GraphAssembler().assemble(
            req, (FactBatch(
                (Node("node:a", "symbol", "A"), Node("node:b", "symbol", "B")),
                (missing,),
            ),), receipt,
        )
    with pytest.raises(ValueError, match="another scope"):
        GraphAssembler().assemble(
            req, (FactBatch(evidence=(replace(ev1, scope_id="other"),)),), receipt,
        )


def test_placeholder_creation_requires_explicit_unresolved_evidence():
    req, scope, receipt, ev1, ev2 = fixture()
    observed_missing = replace(ev2, observation_status="UNRESOLVED")
    unresolved = UnresolvedTarget("node:external", "unknown", observed_missing.id)
    edge = Edge(graph_edge_id("node:a", "node:external", "REFERENCES"), "node:a", "node:external", "REFERENCES",
                evidence_ids=(ev1.id,))
    batch = FactBatch(
        (Node("node:a", "symbol", "A", evidence_ids=(ev1.id,)),),
        (edge,), (ev1, observed_missing,), (unresolved,),
    )
    result = GraphAssembler().assemble(req, (batch,), receipt)
    assert result.status == "PARTIAL"
    assert result.graph.nodes_by_id()["node:external"].kind == "unresolved"
    assert result.receipt.unresolved == ("UNRESOLVED_REFERENCE:node:external",)
    with pytest.raises(ValueError, match="UNRESOLVED_PROVENANCE_REQUIRED"):
        GraphAssembler().assemble(
            req,
            (replace(batch, evidence=(ev1, ev2,)),),
            receipt,
        )


def test_multigraph_parallel_edges_cycles_are_preserved():
    req, scope, receipt, ev1, ev2 = fixture()
    nodes = (
        Node("node:a", "symbol", "A"),
        Node("node:b", "symbol", "B"),
        Node("node:c", "symbol", "C"),
    )
    edges = (
        Edge(graph_edge_id("node:a", "node:b", "CALLS"), "node:a", "node:b", "CALLS", evidence_ids=("ev:1",)),
        Edge(graph_edge_id("node:a", "node:b", "IMPORTS"), "node:a", "node:b", "IMPORTS", evidence_ids=("ev:1",)),
        Edge(graph_edge_id("node:c", "node:b", "CALLS"), "node:c", "node:b", "CALLS", evidence_ids=("ev:1",)),
        Edge(graph_edge_id("node:b", "node:a", "CALLS"), "node:b", "node:a", "CALLS", evidence_ids=("ev:2",)),
    )
    graph = GraphAssembler().assemble(
        req, (FactBatch(nodes, edges, (ev1, ev2)),), receipt,
    ).graph
    assert len(graph.edges) == 4
    assert graph.scope.completeness == "COMPLETE"
    assert [edge.target_id for edge in graph.edges].count("node:b") == 3



def test_runtime_evidence_cannot_be_imported_from_different_head():
    req, scope, receipt, ev1, ev2 = fixture()
    run = Evidence(
        "ev:run", "RUNTIME", "https://github.com/org/repo/actions/runs/1",
        "GITHUB_ACTIONS_RUN", scope, observation_status="RUNTIME_OBSERVED",
        attributes={"source_sha": "b" * 40, "run_id": 1,
                    "attempt": 1, "url": "https://example.invalid/run/1"},
    )
    with pytest.raises(ValueError, match="CROSS_HEAD_RUNTIME_EVIDENCE"):
        GraphAssembler().assemble(req, (FactBatch(evidence=(run,)),), receipt)
    missing_receipt = replace(
        run, attributes={"source_sha": req.revision, "run_id": 1},
    )
    with pytest.raises(ValueError, match="RUNTIME_RECEIPT_INCOMPLETE"):
        GraphAssembler().assemble(
            req, (FactBatch(evidence=(missing_receipt,)),), receipt,
        )


def test_invalid_noncanonical_edge_id_is_rejected():
    req, scope, receipt, ev1, ev2 = fixture()
    bad = Edge("edge:made_up", "node:a", "node:b", "CALLS",
               evidence_ids=(ev1.id,))
    with pytest.raises(ValueError, match="NONCANONICAL_EDGE_ID"):
        GraphAssembler().assemble(
            req,
            (FactBatch(
                (Node("node:a", "symbol", "A"), Node("node:b", "symbol", "B")),
                (bad,), (ev1,),
            ),),
            receipt,
        )



def test_complete_collection_rejects_unresolved_target_even_without_unresolved_text():
    from physics_harness.code.diagnostics import CollectionResult

    unknown = UnresolvedTarget("node:missing", "missing", "ev:unresolved")
    with pytest.raises(ValueError, match="FALSE_COMPLETE_COLLECTION"):
        CollectionResult(FactBatch(unresolved_targets=(unknown,)), status="COMPLETE")
    partial = CollectionResult(FactBatch(unresolved_targets=(unknown,)), status="PARTIAL")
    assert partial.status == "PARTIAL"


def test_duplicate_unresolved_targets_union_distinct_source_witnesses():
    req, scope, receipt, ev1, ev2 = fixture()
    one = replace(ev1, observation_status="UNRESOLVED")
    two = replace(ev2, observation_status="UNRESOLVED")
    target_one = UnresolvedTarget("node:external", "external", one.id)
    target_two = UnresolvedTarget("node:external", "external", two.id)
    assembler = GraphAssembler()
    batches = (
        FactBatch(evidence=(one,), unresolved_targets=(target_one,)),
        FactBatch(evidence=(two,), unresolved_targets=(target_two,)),
    )
    first = assembler.assemble(req, batches, receipt)
    second = assembler.assemble(req, batches[::-1], receipt)
    assert first.graph == second.graph
    placeholder = first.graph.nodes_by_id()["node:external"]
    assert placeholder.kind == "unresolved"
    assert placeholder.evidence_ids == ("ev:1", "ev:2")
    assert first.receipt.unresolved == ("UNRESOLVED_REFERENCE:node:external",)


def test_duplicate_unresolved_target_name_conflict_is_rejected():
    req, scope, receipt, ev1, ev2 = fixture()
    one = replace(ev1, observation_status="UNRESOLVED")
    two = replace(ev2, observation_status="UNRESOLVED")
    batch = FactBatch(
        evidence=(one, two),
        unresolved_targets=(
            UnresolvedTarget("node:external", "first", one.id),
            UnresolvedTarget("node:external", "second", two.id),
        ),
    )
    with pytest.raises(ValueError, match="UNRESOLVED_TARGET_CONFLICT"):
        GraphAssembler().assemble(req, (batch,), receipt)


def test_unresolved_placeholder_cannot_override_canonical_node():
    req, scope, receipt, ev1, ev2 = fixture()
    witness = replace(ev1, observation_status="UNRESOLVED")
    batch = FactBatch(
        nodes=(Node("node:external", "symbol", "external"),),
        evidence=(witness,),
        unresolved_targets=(
            UnresolvedTarget("node:external", "external", witness.id),
        ),
    )
    with pytest.raises(ValueError, match="UNRESOLVED_CANONICAL_NODE_CONFLICT"):
        GraphAssembler().assemble(req, (batch,), receipt)


def test_existing_unresolved_placeholder_merges_additional_witnesses():
    req, scope, receipt, ev1, ev2 = fixture()
    one = replace(ev1, observation_status="UNRESOLVED")
    two = replace(ev2, observation_status="UNRESOLVED")
    batch = FactBatch(
        nodes=(Node("node:external", "unresolved", "external",
                    evidence_ids=(one.id,)),),
        evidence=(one, two),
        unresolved_targets=(
            UnresolvedTarget("node:external", "external", two.id),
        ),
    )
    result = GraphAssembler().assemble(req, (batch,), receipt)
    assert result.status == "PARTIAL"
    assert result.graph.nodes_by_id()["node:external"].evidence_ids == (
        one.id, two.id,
    )
