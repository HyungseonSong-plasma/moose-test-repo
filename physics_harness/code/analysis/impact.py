"""Generic, source-scoped impact exploration using the canonical Context view."""

from __future__ import annotations

from dataclasses import dataclass

from ..diagnostics.collector import stable_id
from ..diagnostics.receipt import EvidenceReceipt
from ..diagnostics.request import normalized_path
from ..graph import (Context, Edge, Evidence, GraphSnapshot, HierarchyView,
                     Node, RelationSelector, unfold_context)


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


@dataclass(frozen=True, slots=True)
class TargetCoverage:
    """Read-only target report; never proof of a closed consumer universe."""

    target_id: str
    scope_id: str
    revision: str
    related_evidence_ids: tuple[str, ...]
    related_source_paths: tuple[str, ...]
    required_paths: tuple[str, ...]
    missing_required_paths: tuple[str, ...]
    incomplete_paths: tuple[str, ...]
    related_incomplete_paths: tuple[str, ...]
    scope_unresolved: tuple[str, ...]
    unverified_surfaces: tuple[str, ...]
    local_blockers: tuple[str, ...]

    @property
    def complete_within_requested_scope(self) -> bool:
        """Complete only within explicitly requested files and capabilities."""
        return not self.local_blockers

    @property
    def global_consumer_closed(self) -> bool:
        """Local source scans cannot prove global consumer closure."""
        return False

    @property
    def retirement_disposition(self) -> str:
        """Never authorize deletion from bounded source evidence alone."""
        return "HOLD"


def analyze_target_coverage(
    graph: GraphSnapshot,
    receipt: EvidenceReceipt,
    target_id: str,
    *,
    required_paths: tuple[str, ...] = (),
    unverified_surfaces: tuple[str, ...] = (),
) -> TargetCoverage:
    """Attribute target evidence to scanned files, without inventing closure.

    Callers enumerate required paths and unverified consumer surfaces such as
    generators, generated inputs, native runtime and external users. Unknown
    source-scope findings are retained rather than assumed unrelated.
    """
    return _target_coverage(graph, receipt, target_id,
                            required_paths=required_paths,
                            unverified_surfaces=unverified_surfaces)


def _target_coverage(
    graph: GraphSnapshot, receipt: EvidenceReceipt, target_id: str, *,
    required_paths: tuple[str, ...], unverified_surfaces: tuple[str, ...],
    nodes: dict[str, Node] | None = None,
    evidence: dict[str, Evidence] | None = None,
    incident_edges: list[Edge] | None = None,
) -> TargetCoverage:
    """Use only internal, same-snapshot indexes when already built by Usage Matrix."""
    if not isinstance(graph, GraphSnapshot):
        raise TypeError("graph must be a GraphSnapshot")
    if not isinstance(receipt, EvidenceReceipt):
        raise TypeError("receipt must be an EvidenceReceipt")
    if (graph.scope.id != receipt.scope_id
            or graph.scope.repository != receipt.repository
            or graph.scope.revision != receipt.revision):
        raise ValueError("TARGET_COVERAGE_SCOPE_MISMATCH")
    if not isinstance(required_paths, tuple):
        raise TypeError("required_paths must be a tuple")
    if not isinstance(unverified_surfaces, tuple):
        raise TypeError("unverified_surfaces must be a tuple")
    for path in required_paths:
        normalized_path(path)
    if any(not isinstance(s, str) or not s.strip() for s in unverified_surfaces):
        raise ValueError("INVALID_TARGET_SURFACE")
    if len(set(required_paths)) != len(required_paths):
        raise ValueError("DUPLICATE_TARGET_REQUIRED_PATH")
    if len(set(unverified_surfaces)) != len(unverified_surfaces):
        raise ValueError("DUPLICATE_TARGET_SURFACE")

    nodes = graph.nodes_by_id() if nodes is None else nodes
    if not isinstance(target_id, str) or target_id not in nodes:
        raise ValueError("UNKNOWN_TARGET_COVERAGE_NODE")

    listed = {file.path: file for file in receipt.files}
    included = tuple(sorted(
        path for path, file in listed.items() if file.status != "EXCLUDED"
    ))
    excluded = tuple(sorted(
        path for path, file in listed.items() if file.status == "EXCLUDED"
    ))
    if (graph.scope.included_paths != included
            or graph.scope.excluded_paths != excluded):
        raise ValueError("TARGET_COVERAGE_RECEIPT_GRAPH_PATH_MISMATCH")

    related_ids = set(nodes[target_id].evidence_ids)
    for edge in graph.edges if incident_edges is None else incident_edges:
        if edge.source_id == target_id or edge.target_id == target_id:
            related_ids.update(edge.evidence_ids)

    by_id = graph.evidence_by_id() if evidence is None else evidence
    related_sources = set()
    for evidence_id in related_ids:
        ev = by_id[evidence_id]
        for path in listed:
            if ev.source_ref.startswith((path + ":", path + "@")):
                related_sources.add(path)

    missing = tuple(sorted(
        path for path in required_paths
        if path not in listed or listed[path].status == "EXCLUDED"
    ))
    incomplete = tuple(sorted(
        path for path, file in listed.items()
        if file.status not in {"SCANNED", "EXCLUDED"}
    ))
    related_incomplete = tuple(sorted(related_sources.intersection(incomplete)))
    unresolved = tuple(sorted(
        set(graph.scope.unresolved) | set(receipt.unresolved)
    ))
    blockers: set[str] = set()
    if not required_paths:
        blockers.add("TARGET_REQUIRED_PATHS_UNDECLARED")
    if missing:
        blockers.add("TARGET_REQUIRED_PATHS_NOT_SCANNED")
    if incomplete:
        blockers.add("INCOMPLETE_REQUESTED_FILES")
    if unresolved:
        blockers.add("UNRESOLVED_REQUESTED_SCOPE")
    if graph.scope.completeness != "COMPLETE" or receipt.completeness != "COMPLETE":
        blockers.add("INCOMPLETE_REQUESTED_SCOPE")
    if not related_ids:
        blockers.add("TARGET_EVIDENCE_ABSENT")
    if any(by_id[evidence_id].observation_status == "UNRESOLVED"
           for evidence_id in related_ids):
        blockers.add("UNRESOLVED_TARGET_EVIDENCE")

    return TargetCoverage(
        target_id=target_id, scope_id=graph.scope.id,
        revision=graph.scope.revision,
        related_evidence_ids=tuple(sorted(related_ids)),
        related_source_paths=tuple(sorted(related_sources)),
        required_paths=tuple(sorted(required_paths)),
        missing_required_paths=missing,
        incomplete_paths=incomplete,
        related_incomplete_paths=related_incomplete,
        scope_unresolved=unresolved,
        unverified_surfaces=tuple(sorted(unverified_surfaces)),
        local_blockers=tuple(sorted(blockers)),
    )


__all__ = [
    "ImpactResult", "analyze_impact",
    "TargetCoverage", "analyze_target_coverage",
]
