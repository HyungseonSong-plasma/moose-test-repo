"""Dynamic, context-scoped parent-child hierarchy projections."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, replace

from ._validation import instance_tuple, nonempty, string_tuple
from .evidence import OBSERVATION_STATUSES
from .scope import GraphSnapshot


DIRECTIONS = frozenset({"FORWARD", "REVERSE"})
OCCURRENCE_STATUSES = frozenset({"NORMAL", "CYCLE_REF", "TRUNCATED"})


@dataclass(frozen=True, slots=True)
class RelationSelector:
    relation: str
    direction: str = "FORWARD"

    def __post_init__(self) -> None:
        nonempty(self.relation, "selector.relation")
        if self.direction not in DIRECTIONS:
            raise ValueError(f"unknown relation direction: {self.direction!r}")


@dataclass(frozen=True, slots=True)
class Context:
    id: str
    roots: tuple[str, ...]
    selectors: tuple[RelationSelector, ...]
    scope_id: str
    evidence_filter: tuple[str, ...] = ()
    max_depth: int = 10
    max_occurrences: int = 10_000

    def __post_init__(self) -> None:
        nonempty(self.id, "context.id")
        nonempty(self.scope_id, "context.scope_id")
        string_tuple(self.roots, "context.roots")
        if not self.roots:
            raise ValueError("context.roots must not be empty")
        instance_tuple(self.selectors, RelationSelector, "context.selectors")
        if len(self.selectors) != len(set(self.selectors)):
            raise ValueError("context.selectors must not contain duplicates")
        string_tuple(self.evidence_filter, "context.evidence_filter")
        if set(self.evidence_filter) - OBSERVATION_STATUSES:
            raise ValueError("context.evidence_filter contains unknown observation states")
        if type(self.max_depth) is not int or self.max_depth < 0:
            raise ValueError("context.max_depth must be a nonnegative integer")
        if type(self.max_occurrences) is not int or self.max_occurrences < 1:
            raise ValueError("context.max_occurrences must be a positive integer")


@dataclass(frozen=True, slots=True)
class NodeOccurrence:
    id: str
    context_id: str
    node_id: str
    parent_occurrence_id: str | None
    via_edge_id: str | None
    status: str = "NORMAL"
    shared: bool = False
    truncation_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("id", "context_id", "node_id"):
            nonempty(getattr(self, name), f"occurrence.{name}")
        if self.parent_occurrence_id is None and self.via_edge_id is not None:
            raise ValueError("root occurrence cannot have an incoming edge")
        if self.parent_occurrence_id is not None:
            nonempty(self.parent_occurrence_id, "occurrence.parent_occurrence_id")
            nonempty(self.via_edge_id, "occurrence.via_edge_id")
        if self.status not in OCCURRENCE_STATUSES:
            raise ValueError(f"unknown occurrence status: {self.status!r}")
        if type(self.shared) is not bool:
            raise TypeError("occurrence.shared must be a boolean")
        if (self.status == "TRUNCATED") != (self.truncation_reason is not None):
            raise ValueError("only TRUNCATED occurrences have a truncation reason")
        if self.truncation_reason is not None:
            nonempty(self.truncation_reason, "occurrence.truncation_reason")


@dataclass(frozen=True, slots=True)
class HierarchyView:
    context_id: str
    occurrences: tuple[NodeOccurrence, ...]
    truncated: bool

    def __post_init__(self) -> None:
        nonempty(self.context_id, "view.context_id")
        instance_tuple(self.occurrences, NodeOccurrence, "view.occurrences")
        if type(self.truncated) is not bool:
            raise TypeError("view.truncated must be a boolean")


def unfold_context(graph: GraphSnapshot, context: Context) -> HierarchyView:
    """Deterministically unfold selected graph edges without mutating the graph.

    A path-local ancestor set detects cycles; a separate seen set only
    annotates shared occurrences and never suppresses distinct paths.
    Budgets make an incomplete unfolding explicit. Context names are free-form;
    only relation selectors and evidence filters determine the traversal.
    """
    if not isinstance(graph, GraphSnapshot) or not isinstance(context, Context):
        raise TypeError("unfold_context requires GraphSnapshot and Context")
    if graph.scope.id != context.scope_id:
        raise ValueError("context scope does not match graph snapshot")
    node_ids = {node.id for node in graph.nodes}
    for root in context.roots:
        if root not in node_ids:
            raise ValueError(f"context root not present in graph: {root}")

    selectors = {(item.relation, item.direction) for item in context.selectors}
    evidence = graph.evidence_by_id()
    adjacency: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for edge in graph.edges:
        if context.evidence_filter and not any(
            evidence[evidence_id].observation_status in context.evidence_filter
            for evidence_id in edge.evidence_ids
        ):
            continue
        if (edge.relation, "FORWARD") in selectors:
            adjacency[edge.source_id].append(
                (edge.id, edge.target_id, "FORWARD")
            )
        if (edge.relation, "REVERSE") in selectors:
            adjacency[edge.target_id].append(
                (edge.id, edge.source_id, "REVERSE")
            )
    for neighbors in adjacency.values():
        neighbors.sort()

    occurrences: list[NodeOccurrence] = []
    seen: set[str] = set()
    truncated = False

    def occurrence_id(path: tuple[str, ...]) -> str:
        payload = json.dumps((context.id, path), ensure_ascii=False, separators=(",", ":"))
        return "occ:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def mark_truncated(index: int, reason: str) -> None:
        nonlocal truncated
        truncated = True
        if occurrences[index].status == "NORMAL":
            occurrences[index] = replace(
                occurrences[index], status="TRUNCATED", truncation_reason=reason
            )

    def visit(
        node_id: str,
        path: tuple[str, ...],
        parent_id: str | None,
        edge_id: str | None,
        ancestors: frozenset[str],
        depth: int,
    ) -> None:
        # Explicit depth-first frames preserve the exact recursive preorder
        # while allowing a bounded traversal deeper than Python's call stack.
        frames = [("enter", node_id, path, parent_id, edge_id, ancestors, depth)]
        while frames:
            action, *state = frames.pop()
            if action == "resume":
                index, this_id, parent_path, lineage, level, neighbors, position = state
                if position >= len(neighbors):
                    continue
                if len(occurrences) >= context.max_occurrences:
                    mark_truncated(index, "MAX_OCCURRENCES")
                    continue
                next_edge_id, child, direction = neighbors[position]
                frames.append((
                    "resume", index, this_id, parent_path, lineage,
                    level, neighbors, position + 1,
                ))
                frames.append((
                    "enter", child, parent_path + (f"{direction}:{next_edge_id}",),
                    this_id, next_edge_id, lineage, level + 1,
                ))
                continue

            current, current_path, parent, incoming_edge, lineage, level = state
            cycle = current in lineage
            this_id = occurrence_id(current_path)
            index = len(occurrences)
            occurrences.append(
                NodeOccurrence(
                    id=this_id,
                    context_id=context.id,
                    node_id=current,
                    parent_occurrence_id=parent,
                    via_edge_id=incoming_edge,
                    status="CYCLE_REF" if cycle else "NORMAL",
                    shared=current in seen,
                )
            )
            seen.add(current)
            if cycle:
                continue

            neighbors = adjacency.get(current, ())
            if level >= context.max_depth:
                if neighbors:
                    mark_truncated(index, "MAX_DEPTH")
                continue
            if neighbors:
                frames.append((
                    "resume", index, this_id, current_path,
                    lineage | {current}, level, neighbors, 0,
                ))

    for root in context.roots:
        if len(occurrences) >= context.max_occurrences:
            mark_truncated(len(occurrences) - 1, "MAX_OCCURRENCES")
            break
        visit(root, (f"root:{root}",), None, None, frozenset(), 0)

    return HierarchyView(
        context_id=context.id,
        occurrences=tuple(occurrences),
        truncated=truncated,
    )
