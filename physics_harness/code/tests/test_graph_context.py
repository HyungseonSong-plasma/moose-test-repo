"""P0 controls for context-specific multi-parent/cycle-safe unfolding."""

from __future__ import annotations

import unittest

from physics_harness.code.graph import (
    Context,
    Edge,
    Evidence,
    GraphSnapshot,
    Node,
    RelationSelector,
    Scope,
    unfold_context,
)


def sample_graph():
    return GraphSnapshot(
        scope=Scope("scope:1", "example/repo", "b" * 40, completeness="PARTIAL"),
        nodes=tuple(Node(f"node:{name}", "symbol", name) for name in "ABCD"),
        edges=(
            Edge("edge:AC", "node:A", "node:C", "R1"),
            Edge("edge:BC", "node:B", "node:C", "R1"),
            Edge("edge:CD", "node:C", "node:D", "R1"),
            Edge("edge:DA", "node:D", "node:A", "R1"),
            Edge("edge:AB", "node:A", "node:B", "R2"),
        ),
    )


def context(**changes):
    options = dict(
        id="unrestricted-user-context",
        roots=("node:A", "node:B"),
        selectors=(RelationSelector("R1"),),
        scope_id="scope:1",
    )
    options.update(changes)
    return Context(**options)


class ContextProjectionTests(unittest.TestCase):
    def test_multiple_parents_cycles_and_shared_paths(self):
        graph = sample_graph()
        view = unfold_context(graph, context())
        # A/C/D/A(cycle) and B/C/D/A/C(cycle): canonical nodes unchanged.
        self.assertEqual(len(view.occurrences), 9)
        self.assertFalse(view.truncated)
        self.assertEqual(
            sum(item.status == "CYCLE_REF" for item in view.occurrences), 2,
        )
        self.assertEqual(len(graph.nodes), 4)
        self.assertEqual(len(graph.edges), 5)
        c_occurrences = [item for item in view.occurrences if item.node_id == "node:C"]
        self.assertEqual(len(c_occurrences), 3)
        self.assertTrue(any(item.shared for item in c_occurrences))

    def test_projection_references_existing_edges(self):
        graph = sample_graph()
        view = unfold_context(graph, context())
        edge_ids = set(graph.edges_by_id())
        for occurrence in view.occurrences:
            if occurrence.parent_occurrence_id is not None:
                self.assertIn(occurrence.via_edge_id, edge_ids)
        self.assertEqual(graph.edges[0].source_id, "node:A")

    def test_arbitrary_context_name_and_reverse_direction(self):
        graph = sample_graph()
        reversed_ctx = context(
            id="whatever-name-user-wants", roots=("node:C",),
            selectors=(RelationSelector("R1", "REVERSE"),), max_depth=1,
        )
        view = unfold_context(graph, reversed_ctx)
        self.assertEqual([item.node_id for item in view.occurrences],
                         ["node:C", "node:A", "node:B"])
        self.assertTrue(view.truncated)
        self.assertEqual(
            sum(item.status == "TRUNCATED" for item in view.occurrences), 1,
        )

    def test_parallel_edges_are_distinct_occurrences(self):
        graph = GraphSnapshot(
            scope=Scope("scope:1", "example/repo", "b" * 40),
            nodes=(Node("node:A", "function", "A"), Node("node:B", "function", "B")),
            edges=(
                Edge("edge:one", "node:A", "node:B", "CALLS"),
                Edge("edge:two", "node:A", "node:B", "CALLS"),
            ),
        )
        ctx = context(roots=("node:A",), selectors=(RelationSelector("CALLS"),))
        view = unfold_context(graph, ctx)
        self.assertEqual(len(view.occurrences), 3)
        self.assertEqual(len({item.id for item in view.occurrences}), 3)
        self.assertTrue(view.occurrences[2].shared)

    def test_depth_and_occurrence_limits_are_explicit(self):
        graph = sample_graph()
        depth = unfold_context(graph, context(max_depth=0))
        self.assertTrue(depth.truncated)
        self.assertEqual(len(depth.occurrences), 2)
        self.assertTrue(all(item.status == "TRUNCATED" for item in depth.occurrences))
        limited = unfold_context(graph, context(max_occurrences=3))
        self.assertTrue(limited.truncated)
        self.assertLessEqual(len(limited.occurrences), 3)
        self.assertIn("MAX_OCCURRENCES", {
            item.truncation_reason for item in limited.occurrences
        })

    def test_missing_root_and_scope_mismatch_fail(self):
        graph = sample_graph()
        with self.assertRaisesRegex(ValueError, "root not present"):
            unfold_context(graph, context(roots=("node:absent",)))
        with self.assertRaisesRegex(ValueError, "scope does not match"):
            unfold_context(graph, context(scope_id="scope:other"))

    def test_static_and_observed_evidence_filters_remain_distinct(self):
        evidence = (
            Evidence("ev:static", "structure", "src/source.py:3", "AST", "scope:1"),
            Evidence(
                "ev:runtime", "runtime", "run:1", "RUN", "scope:1",
                observation_status="RUNTIME_OBSERVED",
            ),
        )
        graph = GraphSnapshot(
            scope=Scope("scope:1", "example/repo", "b" * 40),
            nodes=tuple(Node(f"node:{name}", "symbol", name) for name in "ABC"),
            edges=(
                Edge("edge:static", "node:A", "node:B", "CALLS",
                     evidence_ids=("ev:static",)),
                Edge("edge:observed", "node:A", "node:C", "CALLS",
                     evidence_ids=("ev:runtime",)),
            ),
            evidence=evidence,
        )
        ctx = context(
            roots=("node:A",), selectors=(RelationSelector("CALLS"),),
            evidence_filter=("RUNTIME_OBSERVED",),
        )
        view = unfold_context(graph, ctx)
        self.assertEqual([item.node_id for item in view.occurrences],
                         ["node:A", "node:C"])

    def test_cyclic_self_loop_has_reference_and_no_recursion(self):
        graph = GraphSnapshot(
            scope=Scope("scope:1", "example/repo", "b" * 40),
            nodes=(Node("node:A", "symbol", "A"),),
            edges=(Edge("edge:self", "node:A", "node:A", "DEPENDS_ON"),),
        )
        ctx = context(
            roots=("node:A",), selectors=(RelationSelector("DEPENDS_ON"),),
        )
        view = unfold_context(graph, ctx)
        self.assertEqual([item.status for item in view.occurrences],
                         ["NORMAL", "CYCLE_REF"])
        self.assertFalse(view.truncated)

    def test_invalid_context_parameters_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "max_depth"):
            context(max_depth=-1)
        with self.assertRaisesRegex(ValueError, "duplicates"):
            context(selectors=(RelationSelector("R1"), RelationSelector("R1")))
        with self.assertRaisesRegex(ValueError, "unknown observation states"):
            context(evidence_filter=("MADE_UP_RUNTIME_PASS",))

    def test_both_directions_multiple_roots_preserve_full_view_identity(self):
        graph = GraphSnapshot(
            scope=Scope("scope:1", "example/repo", "b" * 40),
            nodes=(Node("node:A", "symbol", "A"), Node("node:B", "symbol", "B")),
            edges=(Edge("edge:AB", "node:A", "node:B", "CALLS"),),
        )
        selectors = (RelationSelector("CALLS"), RelationSelector("CALLS", "REVERSE"))
        ctx = context(roots=("node:A", "node:B"), selectors=selectors)
        view = unfold_context(graph, ctx)
        reverse_order = unfold_context(graph, context(
            roots=ctx.roots, selectors=selectors[::-1],
        ))

        self.assertEqual(view, reverse_order)
        self.assertEqual(
            [o.node_id for o in view.occurrences],
            ["node:A", "node:B", "node:A", "node:B", "node:A", "node:B"],
        )
        self.assertEqual(
            [o.status for o in view.occurrences],
            ["NORMAL", "NORMAL", "CYCLE_REF", "NORMAL", "NORMAL", "CYCLE_REF"],
        )
        self.assertEqual(
            [o.shared for o in view.occurrences],
            [False, False, True, True, True, True],
        )
        self.assertFalse(view.truncated)
        self.assertEqual(len({o.id for o in view.occurrences}), 6)

        bounded = unfold_context(graph, context(
            roots=ctx.roots, selectors=selectors, max_occurrences=2,
        ))
        self.assertTrue(bounded.truncated)
        self.assertEqual(
            [o.truncation_reason for o in bounded.occurrences],
            [None, "MAX_OCCURRENCES"],
        )


    def test_iterative_deep_chain_exceeds_python_recursion_limit(self):
        count = 1250
        graph = GraphSnapshot(
            scope=Scope("scope:1", "example/repo", "b" * 40),
            nodes=tuple(Node(f"node:{i}", "symbol", str(i)) for i in range(count)),
            edges=tuple(
                Edge(f"edge:{i}", f"node:{i}", f"node:{i + 1}", "DEPENDS_ON")
                for i in range(count - 1)
            ),
        )
        ctx = context(
            roots=("node:0",), selectors=(RelationSelector("DEPENDS_ON"),),
            max_depth=1500, max_occurrences=1500,
        )
        view = unfold_context(graph, ctx)
        self.assertEqual(len(view.occurrences), count)
        self.assertFalse(view.truncated)
        self.assertEqual(view.occurrences[-1].node_id, f"node:{count - 1}")
        self.assertEqual(len({item.id for item in view.occurrences}), count)
        self.assertEqual(view, unfold_context(graph, ctx))

    def test_deep_cycle_and_bounded_traversal_are_explicit(self):
        count = 1150
        graph = GraphSnapshot(
            scope=Scope("scope:1", "example/repo", "b" * 40),
            nodes=tuple(Node(f"node:{i}", "symbol", str(i)) for i in range(count)),
            edges=tuple(
                Edge(f"edge:{i}", f"node:{i}", f"node:{i + 1}", "DEPENDS_ON")
                for i in range(count - 1)
            ) + (
                Edge("edge:back", f"node:{count - 1}", "node:600", "DEPENDS_ON"),
            ),
        )
        full = unfold_context(graph, context(
            roots=("node:0",), selectors=(RelationSelector("DEPENDS_ON"),),
            max_depth=1500, max_occurrences=1500,
        ))
        self.assertFalse(full.truncated)
        self.assertEqual(len(full.occurrences), count + 1)
        self.assertEqual(full.occurrences[-1].status, "CYCLE_REF")
        self.assertEqual(full.occurrences[-1].node_id, "node:600")
        self.assertTrue(full.occurrences[-1].shared)

        bounded = unfold_context(graph, context(
            roots=("node:0",), selectors=(RelationSelector("DEPENDS_ON"),),
            max_depth=1500, max_occurrences=1100,
        ))
        self.assertTrue(bounded.truncated)
        self.assertEqual(len(bounded.occurrences), 1100)
        self.assertIn("MAX_OCCURRENCES", {
            item.truncation_reason for item in bounded.occurrences
        })


if __name__ == "__main__":
    unittest.main()
