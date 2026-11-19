"""Generic, source-scoped impact exploration using the canonical Context view."""

from __future__ import annotations

from dataclasses import dataclass

from ..diagnostics.collector import stable_id
from ..graph import Context, GraphSnapshot, HierarchyView, RelationSelector, unfold_context


@dataclass(frozen=True, slots=True)
class ImpactResult:
    view: HierarchyView
    roots: tuple[str, ...]
    visited_nodes: tuple[str, ...]
    visited_edges: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def complete_within_scope(self) -> bool:
        return not self.blockers


def analyze_impact(
    graph: GraphSnapshot,
    roots: tuple[str, ...],
    relations: tuple[str, ...],
    *,
    direction: str = "REVERSE",
    evidence_filter: tuple[str, ...] = (),
    max_depth: int = 10,
    max_occurrences: int = 10_000,
) -> ImpactResult:
    """Return exact graph paths without inventing missing consumers.

    The result is bounded to the source Scope and relation selectors supplied.
    COMPLETE never asserts that unknown external consumers do not exist.
    """
    if not isinstance(graph, GraphSnapshot):
        raise TypeError("graph must be a GraphSnapshot")
    selectors = tuple(RelationSelector(r, direction) for r in relations)
    context = Context(
        id=stable_id(
            "impact", graph.scope.id, roots, relations,
            direction, evidence_filter, max_depth, max_occurrences,
        ),
        roots=roots, selectors=selectors, scope_id=graph.scope.id,
        evidence_filter=evidence_filter, max_depth=max_depth,
        max_occurrences=max_occurrences,
    )
    view = unfold_context(graph, context)
    visited_nodes = tuple(sorted({o.node_id for o in view.occurrences}))
    visited_edges = tuple(sorted({
        o.via_edge_id for o in view.occurrences if o.via_edge_id is not None
    }))
    nodes = graph.nodes_by_id()
    blockers = set(graph.scope.unresolved)
    if graph.scope.completeness != "COMPLETE":
        blockers.add(f"INCOMPLETE_GRAPH_SCOPE:{graph.scope.completeness}")
    if not relations:
        blockers.add("NO_RELATION_SELECTORS")
    if view.truncated:
        blockers.add("CONTEXT_TRUNCATED")
    for node_id in visited_nodes:
        if nodes[node_id].kind == "unresolved":
            blockers.add(f"UNRESOLVED_TARGET:{node_id}")
    return ImpactResult(
        view=view, roots=roots, visited_nodes=visited_nodes,
        visited_edges=visited_edges, blockers=tuple(sorted(blockers)),
    )


__all__ = ["ImpactResult", "analyze_impact"]
