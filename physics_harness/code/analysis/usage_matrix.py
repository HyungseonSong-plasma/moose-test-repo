"""Read-only, evidence-linked usage screening across multiple Graph targets.

A Usage Matrix is a projection of explicitly selected adjacent relationships.
It does not resolve dynamic callers, establish global consumer closure, or
approve code/resource retirement. Domain-specific relation choices are inputs.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..diagnostics.receipt import EvidenceReceipt
from ..graph import GraphSnapshot, RelationSelector
from .impact import TargetCoverage, _target_coverage


@dataclass(frozen=True, slots=True)
class UsageRelation:
    relation: str
    category: str
    direction: str = "REVERSE"

    def __post_init__(self) -> None:
        RelationSelector(self.relation, self.direction)
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValueError("INVALID_USAGE_CATEGORY")


@dataclass(frozen=True, slots=True)
class UsageWitness:
    evidence_id: str
    source_ref: str
    observation_status: str


@dataclass(frozen=True, slots=True)
class UsageReference:
    consumer_id: str
    consumer_name: str
    consumer_kind: str
    edge_id: str
    relation: str
    direction: str
    category: str
    witnesses: tuple[UsageWitness, ...]


@dataclass(frozen=True, slots=True)
class UsageRow:
    target_id: str
    target_name: str
    target_kind: str
    references: tuple[UsageReference, ...]
    unclassified_edge_ids: tuple[str, ...]
    coverage: TargetCoverage
    screening: str  # RETAIN / REVIEW_CANDIDATE / HOLD; not a retirement verdict
    blockers: tuple[str, ...]

    @property
    def identified_consumer_count(self) -> int:
        """Distinct adjacent nodes, not runtime-instantiated callers."""
        return len({ref.consumer_id for ref in self.references})

    @property
    def safe_to_delete(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class UsageMatrix:
    repository: str
    revision: str
    scope_id: str
    relations: tuple[UsageRelation, ...]
    ignored_relations: tuple[str, ...]
    rows: tuple[UsageRow, ...]

    @property
    def mutation_approved(self) -> bool:
        return False

    @property
    def global_consumer_closed(self) -> bool:
        return False

    def to_dict(self) -> dict:
        """Stable, JSON-serializable projection preserving exact source witnesses."""
        return {
            "schema": "code.usage_matrix.v0.1",
            "repository": self.repository,
            "revision": self.revision,
            "scope_id": self.scope_id,
            "relations": [asdict(item) for item in self.relations],
            "ignored_relations": list(self.ignored_relations),
            "global_consumer_closed": False,
            "mutation_approved": False,
            "rows": [
                {**asdict(row),
                 "identified_consumer_count": row.identified_consumer_count,
                 "safe_to_delete": False}
                for row in self.rows
            ],
        }

    def to_markdown(self) -> str:
        """Compact review projection; category counts are distinct graph nodes."""
        def escape(value: str) -> str:
            return value.replace("|", "\\|").replace("\n", " ")

        lines = [
            "| Target | Identified consumers | Categories | Screening | Blockers |",
            "| --- | ---: | --- | --- | --- |",
        ]
        for row in self.rows:
            by_category: dict[str, set[str]] = defaultdict(set)
            for ref in row.references:
                by_category[ref.category].add(ref.consumer_id)
            categories = ", ".join(
                f"{escape(category)}: {len(by_category[category])}"
                for category in sorted(by_category)
            ) or "—"
            blockers = ", ".join(map(escape, row.blockers)) or "—"
            lines.append(
                f"| {escape(row.target_name)} | {row.identified_consumer_count} | "
                f"{categories} | {row.screening} | {blockers} |"
            )
        return "\n".join(lines)


def build_usage_matrix(
    graph: GraphSnapshot,
    receipt: EvidenceReceipt,
    targets: tuple[str, ...],
    relations: tuple[UsageRelation, ...],
    *,
    required_paths: tuple[str, ...] = (),
    unverified_surfaces: tuple[str, ...] = (),
    ignored_relations: tuple[str, ...] = (),
) -> UsageMatrix:
    """Summarize one-hop references; no active-use or caller-zero inference.

    The caller specifies which relation/direction pairs denote possible
    consumers and which known non-consumer relations to exclude. Unclassified
    incident edges and undeclared/unscanned surfaces fail closed to HOLD.
    """
    if not isinstance(graph, GraphSnapshot) or not isinstance(receipt, EvidenceReceipt):
        raise TypeError("USAGE_MATRIX_GRAPH_RECEIPT_REQUIRED")
    if not isinstance(targets, tuple) or not targets or any(
        not isinstance(item, str) or not item for item in targets
    ) or len(set(targets)) != len(targets):
        raise ValueError("INVALID_USAGE_TARGETS")
    if not isinstance(relations, tuple) or not relations or any(
        not isinstance(rule, UsageRelation) for rule in relations
    ):
        raise ValueError("INVALID_USAGE_RELATIONS")
    relation_keys = {(item.relation, item.direction) for item in relations}
    if len(relation_keys) != len(relations):
        raise ValueError("DUPLICATE_USAGE_RELATION_SELECTOR")
    if not isinstance(ignored_relations, tuple) or any(
        not isinstance(item, str) or not item.strip() for item in ignored_relations
    ) or len(set(ignored_relations)) != len(ignored_relations):
        raise ValueError("INVALID_IGNORED_USAGE_RELATIONS")
    if any(item.relation in ignored_relations for item in relations):
        raise ValueError("CONFLICTING_USAGE_RELATION_POLICY")

    nodes = graph.nodes_by_id()
    for target_id in targets:
        if target_id not in nodes:
            raise ValueError(f"UNKNOWN_USAGE_TARGET:{target_id}")
    evidence = graph.evidence_by_id()
    adjacent: dict[str, list] = defaultdict(list)
    for edge in graph.edges:
        adjacent[edge.source_id].append(edge)
        if edge.target_id != edge.source_id:
            adjacent[edge.target_id].append(edge)

    rows = []
    for target_id in sorted(targets):
        coverage = _target_coverage(
            graph, receipt, target_id,
            required_paths=required_paths,
            unverified_surfaces=unverified_surfaces,
            nodes=nodes, evidence=evidence, incident_edges=adjacent[target_id],
        )
        blockers = set(coverage.local_blockers)
        if coverage.unverified_surfaces:
            blockers.add("UNVERIFIED_CONSUMER_SURFACES")
        references = []
        matched_edges: set[str] = set()
        for rule in sorted(relations, key=lambda item: (
            item.relation, item.direction, item.category,
        )):
            for edge in adjacent[target_id]:
                if edge.relation != rule.relation:
                    continue
                if rule.direction == "REVERSE" and edge.target_id != target_id:
                    continue
                if rule.direction == "FORWARD" and edge.source_id != target_id:
                    continue
                matched_edges.add(edge.id)
                consumer_id = (
                    edge.source_id if rule.direction == "REVERSE" else edge.target_id
                )
                if consumer_id == target_id:
                    blockers.add("SELF_REFERENCE_NOT_EXTERNAL_CONSUMER")
                    continue
                consumer = nodes[consumer_id]
                if consumer.kind == "unresolved":
                    blockers.add("UNRESOLVED_CONSUMER_NODE")
                if not edge.evidence_ids:
                    blockers.add("USAGE_EDGE_EVIDENCE_MISSING")
                witnesses = []
                for evidence_id in sorted(edge.evidence_ids):
                    item = evidence[evidence_id]
                    witnesses.append(UsageWitness(
                        evidence_id, item.source_ref, item.observation_status,
                    ))
                    if item.observation_status == "UNRESOLVED":
                        blockers.add("UNRESOLVED_CONSUMER_EVIDENCE")
                    if item.observation_status == "RUNTIME_OBSERVED" and (
                        item.attributes.get("source_sha") != graph.scope.revision
                    ):
                        blockers.add("UNVERIFIED_RUNTIME_REVISION")
                references.append(UsageReference(
                    consumer_id=consumer_id,
                    consumer_name=consumer.name,
                    consumer_kind=consumer.kind,
                    edge_id=edge.id,
                    relation=edge.relation,
                    direction=rule.direction,
                    category=rule.category,
                    witnesses=tuple(witnesses),
                ))
        unclassified = tuple(sorted({
            edge.id for edge in adjacent[target_id]
            if edge.id not in matched_edges and edge.relation not in ignored_relations
        }))
        if unclassified:
            blockers.add("UNCLASSIFIED_INCIDENT_EDGES")
        references.sort(key=lambda item: (
            item.category, item.consumer_id, item.edge_id, item.direction,
        ))
        # An observation from another revision cannot establish a consumer
        # at this exact Graph HEAD, even if its status says RUNTIME_OBSERVED.
        supported = any(
            witness.observation_status == "SOURCE_DECLARED" or (
                witness.observation_status == "RUNTIME_OBSERVED"
                and evidence[witness.evidence_id].attributes.get("source_sha")
                    == graph.scope.revision
            )
            for ref in references for witness in ref.witnesses
        )
        if supported:
            screening = "RETAIN"  # A known reference blocks direct deletion.
        elif blockers or references:
            screening = "HOLD"
        else:
            screening = "REVIEW_CANDIDATE"  # Never global caller-zero proof.
        node = nodes[target_id]
        rows.append(UsageRow(
            target_id=target_id, target_name=node.name, target_kind=node.kind,
            references=tuple(references), unclassified_edge_ids=unclassified,
            coverage=coverage, screening=screening,
            blockers=tuple(sorted(blockers)),
        ))
    return UsageMatrix(
        repository=graph.scope.repository, revision=graph.scope.revision,
        scope_id=graph.scope.id,
        relations=tuple(sorted(relations, key=lambda item: (
            item.relation, item.direction, item.category,
        ))),
        ignored_relations=tuple(sorted(ignored_relations)),
        rows=tuple(rows),
    )


__all__ = [
    "UsageRelation", "UsageWitness", "UsageReference", "UsageRow",
    "UsageMatrix", "build_usage_matrix",
]
