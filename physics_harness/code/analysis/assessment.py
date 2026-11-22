"""Fail-closed generic Evidence → conditional assessment, never auto-approval."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..graph import Claim, GraphSnapshot


@dataclass(frozen=True, slots=True)
class Assessment:
    claim: Claim
    disposition: str
    blockers: tuple[str, ...]
    verification_obligations: tuple[str, ...]

    @property
    def actionable_without_verification(self) -> bool:
        """Never authorize mutations from static or mixed evidence alone."""
        return False


def assess_finding(
    graph: GraphSnapshot,
    claim: Claim,
    *,
    required_evidence_kinds: tuple[str, ...] = (),
    verification_obligations: tuple[str, ...] = (),
) -> Assessment:
    """Rank review candidates; only a separate verification gate can approve.

    COMPLETE is limited to graph Scope, and source declarations are not
    runtime observations. Unsupported/missing evidence always means HOLD.
    """
    if not isinstance(graph, GraphSnapshot) or not isinstance(claim, Claim):
        raise TypeError("assess_finding requires GraphSnapshot and Claim")
    if claim.scope_id != graph.scope.id:
        raise ValueError("CROSS_SCOPE_FINDING")
    if not isinstance(required_evidence_kinds, tuple) or not isinstance(
        verification_obligations, tuple
    ):
        raise TypeError("requirements must be tuples")

    subject_ids = {n.id for n in graph.nodes} | {e.id for e in graph.edges}
    if any(s not in subject_ids for s in claim.subject_refs):
        raise ValueError("UNKNOWN_FINDING_SUBJECT")

    source_evidence = graph.evidence_by_id()
    supporting = []
    refuting = []
    qualifying = []
    for link in claim.evidence_refs:
        if link.evidence_id not in source_evidence:
            raise ValueError(f"UNKNOWN_FINDING_EVIDENCE:{link.evidence_id}")
        ev = source_evidence[link.evidence_id]
        if link.role == "SUPPORTS":
            supporting.append(ev)
        elif link.role == "REFUTES":
            refuting.append(ev)
        else:
            qualifying.append(ev)

    blockers: set[str] = set(graph.scope.unresolved)
    if graph.scope.completeness != "COMPLETE":
        blockers.add(f"INCOMPLETE_GRAPH_SCOPE:{graph.scope.completeness}")
    if not supporting:
        blockers.add("NO_SUPPORTING_EVIDENCE")
    if not required_evidence_kinds:
        blockers.add("REQUIRED_EVIDENCE_CONTRACT_MISSING")
    present_kinds = {ev.kind for ev in supporting}
    for kind in required_evidence_kinds:
        if kind not in present_kinds:
            blockers.add(f"REQUIRED_EVIDENCE_MISSING:{kind}")
    if qualifying:
        blockers.add("QUALIFYING_EVIDENCE_REQUIRES_REVIEW")
    if claim.conditions:
        blockers.add("CONDITIONAL_ASSUMPTIONS_NOT_VERIFIED")

    for ev in (*supporting, *refuting, *qualifying):
        if ev.observation_status == "UNRESOLVED":
            blockers.add(f"UNRESOLVED_EVIDENCE:{ev.id}")
        if ev.observation_status == "RUNTIME_OBSERVED":
            if ev.attributes.get("source_sha") != graph.scope.revision:
                blockers.add(f"CROSS_HEAD_RUNTIME_EVIDENCE:{ev.id}")

    if refuting:
        status, disposition = "REFUTED", "BLOCKED"
        blockers.add("REFUTING_EVIDENCE")
    elif blockers:
        status, disposition = "UNRESOLVED", "HOLD"
    else:
        status, disposition = "QUALIFIED", "CANDIDATE_FOR_VERIFICATION"

    updated_claim = replace(claim, assessment_status=status)
    return Assessment(
        claim=updated_claim, disposition=disposition,
        blockers=tuple(sorted(blockers)),
        verification_obligations=tuple(sorted(set(verification_obligations))),
    )

# Keep historical direct imports stable for existing external consumers.
from .parameter_contract import (
    ParameterBlockAssessment, ParameterContractAssessment,
    assess_input_parameter_contract,
)


__all__ = [
    "Assessment", "assess_finding",
    "ParameterBlockAssessment", "ParameterContractAssessment",
    "assess_input_parameter_contract",
]
