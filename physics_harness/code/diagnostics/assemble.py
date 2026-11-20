"""Deterministic, fail-closed assembly of collector facts into GraphSnapshot."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..graph import Edge, Evidence, GraphSnapshot, Node, Scope
from .collector import FactBatch, graph_edge_id, scan_scope_id
from .receipt import EvidenceReceipt
from .request import ScanRequest


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    graph: GraphSnapshot
    receipt: EvidenceReceipt
    verification: object | None = None

    @property
    def status(self) -> str:
        return self.receipt.completeness


def _combine_evidence_refs(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(left) | set(right)))


class GraphAssembler:
    """Merge in ID order, never overwrite contradictory facts.

    Evidence is mandatory on each diagnostic edge. Graph itself is deliberately
    more general and can store edge records created outside Diagnostics.
    """

    def assemble(self, request: ScanRequest, batches: tuple[FactBatch, ...],
                 receipt: EvidenceReceipt) -> DiagnosticResult:
        if receipt.scope_id != scan_scope_id(request):
            raise ValueError("DIAGNOSTIC_SCOPE_MISMATCH")
        if receipt.repository != request.repository or receipt.revision != request.revision:
            raise ValueError("DIAGNOSTIC_REVISION_MISMATCH")
        if not isinstance(batches, tuple) or any(
            not isinstance(batch, FactBatch) for batch in batches
        ):
            raise TypeError("batches must be a tuple of FactBatch")
        nodes: dict[str, Node] = {}
        edges: dict[str, Edge] = {}
        evidence: dict[str, Evidence] = {}
        unresolved_targets = []
        batch_unresolved: set[str] = set(receipt.unresolved)

        for batch in batches:
            batch_unresolved.update(batch.unresolved)
            unresolved_targets.extend(batch.unresolved_targets)
            for item in batch.evidence:
                if item.observation_status == "RUNTIME_OBSERVED":
                    attrs = item.attributes
                    if attrs.get("source_sha") != request.revision:
                        raise ValueError("CROSS_HEAD_RUNTIME_EVIDENCE")
                    if not all(attrs.get(key) for key in ("run_id", "attempt", "url")):
                        raise ValueError("RUNTIME_RECEIPT_INCOMPLETE")
                previous = evidence.get(item.id)
                if previous is not None and previous != item:
                    raise ValueError(f"EVIDENCE_ID_CONFLICT: {item.id}")
                evidence[item.id] = item
            for item in batch.nodes:
                previous = nodes.get(item.id)
                if previous is not None:
                    if replace(previous, evidence_ids=()) != replace(item, evidence_ids=()):
                        raise ValueError(f"NODE_ID_CONFLICT: {item.id}")
                    item = replace(
                        previous, evidence_ids=_combine_evidence_refs(
                            previous.evidence_ids, item.evidence_ids
                        ),
                    )
                nodes[item.id] = item
            for item in batch.edges:
                if item.id != graph_edge_id(
                    item.source_id, item.target_id, item.relation,
                    item.discriminator or "",
                ):
                    raise ValueError(f"NONCANONICAL_EDGE_ID: {item.id}")
                if not item.evidence_ids:
                    raise ValueError(f"EDGE_EVIDENCE_REQUIRED: {item.id}")
                previous = edges.get(item.id)
                if previous is not None:
                    if replace(previous, evidence_ids=()) != replace(item, evidence_ids=()):
                        raise ValueError(f"EDGE_ID_CONFLICT: {item.id}")
                    item = replace(
                        previous, evidence_ids=_combine_evidence_refs(
                            previous.evidence_ids, item.evidence_ids
                        ),
                    )
                edges[item.id] = item

        # Multiple collectors can report the same unresolved identity. The
        # placeholder name must agree; all witnesses are preserved.
        targets: dict[str, tuple[str, set[str]]] = {}
        for target in unresolved_targets:
            witness = evidence.get(target.evidence_id)
            if witness is None or witness.observation_status != "UNRESOLVED":
                raise ValueError(f"UNRESOLVED_PROVENANCE_REQUIRED: {target.node_id}")
            prior = targets.get(target.node_id)
            if prior is None:
                targets[target.node_id] = (target.name, {target.evidence_id})
            else:
                if prior[0] != target.name:
                    raise ValueError(f"UNRESOLVED_TARGET_CONFLICT: {target.node_id}")
                prior[1].add(target.evidence_id)

        for node_id in sorted(targets):
            name, witnesses = targets[node_id]
            existing = nodes.get(node_id)
            if existing is not None and (
                existing.kind != "unresolved" or existing.name != name
            ):
                raise ValueError(f"UNRESOLVED_CANONICAL_NODE_CONFLICT: {node_id}")
            nodes[node_id] = (
                Node(id=node_id, kind="unresolved", name=name,
                     evidence_ids=tuple(sorted(witnesses)))
                if existing is None else replace(
                    existing,
                    evidence_ids=_combine_evidence_refs(
                        existing.evidence_ids, tuple(sorted(witnesses))
                    ),
                )
            )
            batch_unresolved.add(f"UNRESOLVED_REFERENCE:{node_id}")
        # Do not silently invent absent endpoints: only declared unresolved
        # targets may create placeholders. GraphSnapshot checks all refs.
        unresolved = tuple(sorted(batch_unresolved))
        completeness = (
            "COMPLETE" if receipt.completeness == "COMPLETE" and not unresolved
            else "PARTIAL"
        )
        included_paths = tuple(sorted(
            f.path for f in receipt.files if f.status != "EXCLUDED"
        ))
        excluded_paths = tuple(sorted(
            f.path for f in receipt.files if f.status == "EXCLUDED"
        ))
        scope = Scope(
            id=receipt.scope_id, repository=request.repository,
            revision=request.revision, included_paths=included_paths,
            excluded_paths=excluded_paths, completeness=completeness,
            unresolved=unresolved,
        )
        graph = GraphSnapshot(
            scope=scope,
            nodes=tuple(nodes[k] for k in sorted(nodes)),
            edges=tuple(edges[k] for k in sorted(edges)),
            evidence=tuple(evidence[k] for k in sorted(evidence)),
        )
        if completeness != receipt.completeness or unresolved != receipt.unresolved:
            receipt = replace(
                receipt, completeness=completeness, unresolved=unresolved
            )
        # Verify every generated graph/receipt as part of assembly.
        from ..verification import verify_generated_artifact
        verification = verify_generated_artifact(graph, receipt)
        return DiagnosticResult(
            graph=graph, receipt=receipt, verification=verification,
        )
