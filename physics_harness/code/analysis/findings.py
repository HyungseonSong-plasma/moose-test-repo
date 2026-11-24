"""Build traceable issue-specific Claims without duplicating the Graph model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..diagnostics.collector import stable_id
from ..graph import Claim, ClaimEvidenceRef, GraphSnapshot


def propose_finding(
    graph: GraphSnapshot,
    predicate: str,
    subjects: tuple[str, ...],
    *,
    supports: tuple[str, ...] = (),
    refutes: tuple[str, ...] = (),
    qualifies: tuple[str, ...] = (),
    conditions: Mapping[str, Any] | None = None,
) -> Claim:
    """Return an unevaluated Claim; source facts are not automatic verdicts."""
    if not isinstance(graph, GraphSnapshot):
        raise TypeError("graph must be a GraphSnapshot")
    if not isinstance(subjects, tuple):
        raise TypeError("subjects must be a tuple")
    known_subjects = {
        *(node.id for node in graph.nodes),
        *(edge.id for edge in graph.edges),
    }
    for subject in subjects:
        if subject not in known_subjects:
            raise ValueError(f"UNKNOWN_FINDING_SUBJECT:{subject}")
    known_evidence = set(graph.evidence_by_id())
    evidence_refs = []
    for role, ids in (
        ("SUPPORTS", supports), ("REFUTES", refutes),
        ("QUALIFIES", qualifies),
    ):
        if not isinstance(ids, tuple):
            raise TypeError(f"{role} evidence must be a tuple")
        for identifier in ids:
            if identifier not in known_evidence:
                raise ValueError(f"UNKNOWN_FINDING_EVIDENCE:{identifier}")
            evidence_refs.append(ClaimEvidenceRef(identifier, role))
    return Claim(
        id=stable_id("claim", graph.scope.id, predicate, subjects),
        predicate=predicate, subject_refs=subjects,
        scope_id=graph.scope.id, conditions=conditions or {},
        evidence_refs=tuple(sorted(
            evidence_refs, key=lambda ref: (ref.role, ref.evidence_id)
        )),
        assessment_status="NOT_EVALUATED",
    )


__all__ = ["propose_finding"]
