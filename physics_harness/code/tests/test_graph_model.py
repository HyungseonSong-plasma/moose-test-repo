"""P0 controls for graph identity, evidence, claims and source scope."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from physics_harness.code.graph import (
    Claim,
    ClaimEvidenceRef,
    Edge,
    Evidence,
    GraphSnapshot,
    Node,
    Scope,
    SourceLocation,
)


HEAD = "a" * 40


def scope(**changes):
    fields = dict(
        id="scope:1",
        repository="example/repository",
        revision=HEAD,
        included_paths=("src/",),
        completeness="PARTIAL",
    )
    fields.update(changes)
    return Scope(**fields)


def sample():
    ev1 = Evidence(
        id="ev:1", kind="structural", source_ref="src/main.py:5@blob",
        method="PYTHON_AST", scope_id="scope:1",
    )
    ev2 = Evidence(
        id="ev:2", kind="functional", source_ref="run:example/123",
        method="NATIVE_RUN", scope_id="scope:1",
        observation_status="RUNTIME_OBSERVED",
    )
    nodes = (
        Node("node:a", "function", "a", evidence_ids=("ev:1",)),
        Node("node:b", "function", "b"),
    )
    edge = Edge(
        id="edge:1", source_id="node:a", target_id="node:b",
        relation="CALLS", evidence_ids=("ev:1",),
    )
    claim = Claim(
        id="claim:1", predicate="COMPATIBLE_IF",
        subject_refs=("node:a", "node:b"), scope_id="scope:1",
        conditions={"density": {"kind": "constant"}},
        evidence_refs=(
            ClaimEvidenceRef("ev:1", "SUPPORTS"),
            ClaimEvidenceRef("ev:2", "QUALIFIES"),
        ),
        assessment_status="QUALIFIED",
    )
    return GraphSnapshot(
        scope=scope(), nodes=nodes, edges=(edge,),
        evidence=(ev1, ev2), claims=(claim,),
    )


class GraphModelTests(unittest.TestCase):
    def test_valid_snapshot_and_evidence_roles(self):
        graph = sample()
        self.assertEqual(graph.edges[0].relation, "CALLS")
        self.assertEqual(
            tuple(ref.role for ref in graph.claims[0].evidence_refs),
            ("SUPPORTS", "QUALIFIES"),
        )

    def test_attributes_and_conditions_are_deeply_immutable(self):
        source = {"nested": {"tags": ["A"]}}
        node = Node("node:x", "function", "x", attributes=source)
        source["nested"]["tags"].append("B")
        self.assertEqual(node.attributes["nested"]["tags"], ("A",))
        with self.assertRaises(TypeError):
            node.attributes["nested"]["other"] = "wrong"
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            node.name = "mutated"
        conditions = sample().claims[0].conditions
        with self.assertRaises(TypeError):
            conditions["density"]["kind"] = "other"

    def test_source_span_rejects_invalid_positions(self):
        with self.assertRaises(ValueError):
            SourceLocation("src/main.py", start_line=5, end_line=3)
        with self.assertRaises(ValueError):
            SourceLocation("src/main.py", end_line=5)
        self.assertEqual(SourceLocation("src/main.py", 3, 5).end_line, 5)

    def test_dangling_edge_is_rejected(self):
        graph = sample()
        bad_edge = Edge("edge:2", "node:a", "node:missing", "CALLS")
        with self.assertRaisesRegex(ValueError, "missing canonical node"):
            GraphSnapshot(graph.scope, graph.nodes, (bad_edge,), graph.evidence)

    def test_explicit_unresolved_target_is_allowed(self):
        graph = sample()
        unresolved = Node("node:external", "unresolved", "external call")
        external_edge = Edge("edge:external", "node:a", "node:external", "CALLS")
        result = GraphSnapshot(
            graph.scope, graph.nodes + (unresolved,),
            graph.edges + (external_edge,), graph.evidence, graph.claims,
        )
        self.assertIn("node:external", result.nodes_by_id())

    def test_unknown_evidence_and_subject_are_rejected(self):
        graph = sample()
        bad_node = Node("node:new", "file", "new", evidence_ids=("ev:unknown",))
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            GraphSnapshot(graph.scope, graph.nodes + (bad_node,), graph.edges, graph.evidence)
        bad_claim = Claim(
            id="claim:unknown", predicate="EXISTS", subject_refs=("node:missing",),
            scope_id=graph.scope.id,
        )
        with self.assertRaisesRegex(ValueError, "unknown subject"):
            GraphSnapshot(
                graph.scope, graph.nodes, graph.edges, graph.evidence, (bad_claim,),
            )

    def test_duplicate_ids_are_rejected(self):
        graph = sample()
        with self.assertRaisesRegex(ValueError, "duplicate node ID"):
            GraphSnapshot(graph.scope, graph.nodes + graph.nodes[:1], graph.edges, graph.evidence)
        collision = Node("edge:1", "file", "collides")
        with self.assertRaisesRegex(ValueError, "globally distinct"):
            GraphSnapshot(
                graph.scope, graph.nodes + (collision,), graph.edges, graph.evidence,
            )

    def test_scope_mismatch_and_completeness_fail_closed(self):
        graph = sample()
        wrong = Evidence("ev:other", "structural", "src/x.py:1", "AST", "scope:other")
        with self.assertRaisesRegex(ValueError, "another scope"):
            GraphSnapshot(graph.scope, graph.nodes, graph.edges, graph.evidence + (wrong,))
        with self.assertRaisesRegex(ValueError, "cannot be COMPLETE"):
            scope(completeness="COMPLETE", unresolved=("unresolved:include",))
        with self.assertRaisesRegex(ValueError, "exact 40-character"):
            scope(revision="main")

    def test_claim_requires_provenance_for_supported_verdict(self):
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            Claim("claim:unsupported", "EQUAL", ("node:a",), "scope:1",
                  assessment_status="SUPPORTED")
        with self.assertRaisesRegex(ValueError, "unknown claim evidence role"):
            ClaimEvidenceRef("ev:1", "APPROVES")

    def test_source_evidence_is_not_native_observation(self):
        graph = sample()
        self.assertEqual(graph.evidence[0].observation_status, "SOURCE_DECLARED")
        self.assertNotEqual(
            graph.evidence[0].observation_status,
            graph.evidence[1].observation_status,
        )

    def test_duplicate_and_cross_scope_identifiers_keep_exact_errors(self):
        graph = sample()
        with self.assertRaisesRegex(ValueError, "^duplicate evidence ID$"):
            GraphSnapshot(
                graph.scope, graph.nodes, graph.edges,
                graph.evidence + (graph.evidence[0],), graph.claims,
            )
        with self.assertRaisesRegex(ValueError, "^duplicate claim ID$"):
            GraphSnapshot(
                graph.scope, graph.nodes, graph.edges,
                graph.evidence, graph.claims + graph.claims,
            )
        with self.assertRaisesRegex(ValueError, "globally distinct"):
            GraphSnapshot(
                scope(id="node:a"), graph.nodes, graph.edges, graph.evidence,
                graph.claims,
            )
        cross_scope = Claim("claim:other", "REFERENCES", ("node:a",), "other:scope")
        with self.assertRaisesRegex(ValueError, "claim belongs to another scope"):
            GraphSnapshot(
                graph.scope, graph.nodes, graph.edges, graph.evidence,
                (cross_scope,),
            )
        missing_witness = Claim(
            "claim:missing", "REFERENCES", ("node:a",), graph.scope.id,
            evidence_refs=(ClaimEvidenceRef("ev:missing", "SUPPORTS"),),
        )
        with self.assertRaisesRegex(ValueError, "^claim:missing: unknown evidence ev:missing$"):
            GraphSnapshot(
                graph.scope, graph.nodes, graph.edges, graph.evidence,
                (missing_witness,),
            )

    def test_duplicate_claim_links_remain_rejected(self):
        link = ClaimEvidenceRef("ev:1", "SUPPORTS")
        with self.assertRaisesRegex(ValueError, "duplicate claim evidence link"):
            Claim(
                "claim:duplicate-links", "REFERENCES", ("node:a",), "scope:1",
                evidence_refs=(link, link),
            )


    def test_same_evidence_multiple_roles_preserves_existing_contract(self):
        links = (
            ClaimEvidenceRef("ev:1", "SUPPORTS"),
            ClaimEvidenceRef("ev:1", "QUALIFIES"),
        )
        claim = Claim(
            "claim:role-distinct", "REFERENCES", ("node:a",), "scope:1",
            evidence_refs=links,
        )
        self.assertEqual(claim.evidence_refs, links)
        with self.assertRaisesRegex(ValueError, "duplicate claim evidence link"):
            Claim(
                "claim:role-duplicate", "REFERENCES", ("node:a",), "scope:1",
                evidence_refs=links + links[:1],
            )


if __name__ == "__main__":
    unittest.main()
