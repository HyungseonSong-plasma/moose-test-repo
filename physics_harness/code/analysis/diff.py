"""Exact-scope, immutable before/after graph and provenance comparison."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..graph import GraphSnapshot


@dataclass(frozen=True, slots=True)
class GraphDiff:
    before_revision: str
    after_revision: str
    added_nodes: tuple[str, ...]
    removed_nodes: tuple[str, ...]
    changed_nodes: tuple[str, ...]
    added_edges: tuple[str, ...]
    removed_edges: tuple[str, ...]
    changed_edges: tuple[str, ...]
    added_evidence: tuple[str, ...]
    removed_evidence: tuple[str, ...]
    changed_evidence: tuple[str, ...]
    new_unresolved: tuple[str, ...]
    cleared_unresolved: tuple[str, ...]
    coverage_changed: bool

    @property
    def semantic_compatibility_proven(self) -> bool:
        """Identity/evidence comparison is not a semantic proof."""
        return False


def _changes(before: dict, after: dict) -> tuple[
    tuple[str, ...], tuple[str, ...], tuple[str, ...],
]:
    first, second = set(before), set(after)
    return (
        tuple(sorted(second - first)),
        tuple(sorted(first - second)),
        tuple(sorted(k for k in first & second if before[k] != after[k])),
    )


def compare_graphs(before: GraphSnapshot, after: GraphSnapshot) -> GraphDiff:
    """Compare revision-independent identities and source-bound Evidence.

    Ignore only Node/Edge evidence_ids when comparing semantic payloads;
    evidence additions and removals are compared separately. A clean diff
    cannot establish runtime behavior or external consumer closure.
    """
    if not isinstance(before, GraphSnapshot) or not isinstance(after, GraphSnapshot):
        raise TypeError("compare_graphs requires two GraphSnapshot values")
    if before.scope.repository != after.scope.repository:
        raise ValueError("CROSS_REPOSITORY_GRAPH_DIFF")

    def nodes_without_evidence(graph: GraphSnapshot) -> dict:
        return {
            item.id: replace(item, evidence_ids=()) for item in graph.nodes
        }

    def edges_without_evidence(graph: GraphSnapshot) -> dict:
        return {
            item.id: replace(item, evidence_ids=()) for item in graph.edges
        }

    added_nodes, removed_nodes, changed_nodes = _changes(
        nodes_without_evidence(before), nodes_without_evidence(after),
    )
    added_edges, removed_edges, changed_edges = _changes(
        edges_without_evidence(before), edges_without_evidence(after),
    )
    added_evidence, removed_evidence, changed_evidence = _changes(
        before.evidence_by_id(), after.evidence_by_id(),
    )
    first_unresolved = set(before.scope.unresolved)
    second_unresolved = set(after.scope.unresolved)
    coverage_changed = (
        before.scope.included_paths != after.scope.included_paths
        or before.scope.excluded_paths != after.scope.excluded_paths
        or before.scope.completeness != after.scope.completeness
    )
    return GraphDiff(
        before_revision=before.scope.revision,
        after_revision=after.scope.revision,
        added_nodes=added_nodes, removed_nodes=removed_nodes,
        changed_nodes=changed_nodes, added_edges=added_edges,
        removed_edges=removed_edges, changed_edges=changed_edges,
        added_evidence=added_evidence, removed_evidence=removed_evidence,
        changed_evidence=changed_evidence,
        new_unresolved=tuple(sorted(second_unresolved - first_unresolved)),
        cleared_unresolved=tuple(sorted(first_unresolved - second_unresolved)),
        coverage_changed=coverage_changed,
    )


__all__ = ["GraphDiff", "compare_graphs"]
