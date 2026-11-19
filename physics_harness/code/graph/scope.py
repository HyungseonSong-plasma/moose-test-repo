"""Exact-revision scan scope and validated canonical graph snapshots."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._validation import instance_tuple, nonempty, string_tuple
from .claim import Claim
from .edge import Edge
from .evidence import Evidence
from .node import Node


COMPLETENESS_STATUSES = frozenset({"UNKNOWN", "PARTIAL", "COMPLETE"})


@dataclass(frozen=True, slots=True)
class Scope:
    id: str
    repository: str
    revision: str
    included_paths: tuple[str, ...] = ()
    excluded_paths: tuple[str, ...] = ()
    completeness: str = "UNKNOWN"
    unresolved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        nonempty(self.id, "scope.id")
        nonempty(self.repository, "scope.repository")
        if not isinstance(self.revision, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", self.revision):
            raise ValueError("scope.revision must be an exact 40-character Git SHA-1")
        object.__setattr__(self, "revision", self.revision.lower())
        string_tuple(self.included_paths, "scope.included_paths")
        string_tuple(self.excluded_paths, "scope.excluded_paths")
        string_tuple(self.unresolved, "scope.unresolved")
        if set(self.included_paths) & set(self.excluded_paths):
            raise ValueError("scope paths cannot be both included and excluded")
        if self.completeness not in COMPLETENESS_STATUSES:
            raise ValueError(f"unknown scope completeness: {self.completeness!r}")
        if self.completeness == "COMPLETE" and self.unresolved:
            raise ValueError("scope with unresolved findings cannot be COMPLETE")


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    """Immutable collection with fail-closed cross-reference validation.

    A referenced but unresolvable external target must have an explicit
    canonical placeholder Node; dangling edge endpoints are rejected.
    Snapshot validation does not attest scan coverage or runtime activity.
    """

    scope: Scope
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    claims: tuple[Claim, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, Scope):
            raise TypeError("graph.scope must be a Scope")
        for field_name, item_type in (
            ("nodes", Node), ("edges", Edge),
            ("evidence", Evidence), ("claims", Claim),
        ):
            instance_tuple(getattr(self, field_name), item_type, f"graph.{field_name}")
        node_ids = _unique_ids(self.nodes, "node")
        edge_ids = _unique_ids(self.edges, "edge")
        subject_ids = node_ids | edge_ids
        evidence_ids = _unique_ids(self.evidence, "evidence")
        claim_ids = _unique_ids(self.claims, "claim")
        groups = (node_ids, edge_ids, evidence_ids, claim_ids, {self.scope.id})
        if len(set.union(*groups)) != sum(map(len, groups)):
            raise ValueError("IDs must be globally distinct within a graph snapshot")

        for entity in (*self.nodes, *self.edges):
            for evidence_id in entity.evidence_ids:
                if evidence_id not in evidence_ids:
                    raise ValueError(f"{entity.id}: unknown evidence {evidence_id}")
        for edge in self.edges:
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                raise ValueError(f"{edge.id}: missing canonical node endpoint")
        for item in self.evidence:
            if item.scope_id != self.scope.id:
                raise ValueError(f"{item.id}: evidence belongs to another scope")
        for claim in self.claims:
            if claim.scope_id != self.scope.id:
                raise ValueError(f"{claim.id}: claim belongs to another scope")
            for subject in claim.subject_refs:
                if subject not in subject_ids:
                    raise ValueError(f"{claim.id}: unknown subject {subject}")
            for link in claim.evidence_refs:
                if link.evidence_id not in evidence_ids:
                    raise ValueError(f"{claim.id}: unknown evidence {link.evidence_id}")

    def nodes_by_id(self) -> dict[str, Node]:
        return {node.id: node for node in self.nodes}

    def edges_by_id(self) -> dict[str, Edge]:
        return {edge.id: edge for edge in self.edges}

    def evidence_by_id(self) -> dict[str, Evidence]:
        return {item.id: item for item in self.evidence}


def _unique_ids(items: tuple, label: str) -> set[str]:
    ids = [item.id for item in items]
    unique = set(ids)
    if len(ids) != len(unique):
        raise ValueError(f"duplicate {label} ID")
    return unique
