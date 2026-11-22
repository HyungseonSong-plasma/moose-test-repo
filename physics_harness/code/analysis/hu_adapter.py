"""Adapter from code Diagnostics observations to the independent HU library.

No HU scoring equations, code-change advice or refactoring decisions live here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import json

from libs.hu import (HUAssessment, HUInput, HUObservation, StructuralMetric,
                     evaluate_hu, from_python_ast)

if TYPE_CHECKING:
    from ..diagnostics.assemble import DiagnosticResult


def assess_code_hu(
    diagnostic: DiagnosticResult,
    target_id: str,
    *,
    observations: tuple[HUObservation, ...] = (),
) -> HUAssessment:
    """Describe target structure and aggregate source-bound human observations.

    Requires the source blob in the scan receipt. Incomplete scope is retained
    as uncertainty; failed provenance cannot be used for an HU assessment.
    """
    graph, receipt = diagnostic.graph, diagnostic.receipt
    scope = graph.scope
    if (scope.repository != receipt.repository or scope.revision != receipt.revision
            or scope.id != receipt.scope_id):
        raise ValueError("HU_ADAPTER_SCOPE_MISMATCH")
    nodes = graph.nodes_by_id()
    if target_id not in nodes:
        raise ValueError("HU_ADAPTER_UNKNOWN_TARGET")
    target = nodes[target_id]
    path = target.location.path if target.location else None
    record = next((f for f in receipt.files if f.path == path), None)
    if record is None:
        raise ValueError("HU_ADAPTER_TARGET_SOURCE_MISSING")
    verification = diagnostic.verification
    if verification is not None:
        if (verification.scope_id != scope.id
                or verification.repository != scope.repository
                or verification.revision != scope.revision):
            raise ValueError("HU_ADAPTER_VERIFICATION_SCOPE_MISMATCH")
        if verification.status == "FAILED":
            raise ValueError("HU_ADAPTER_PROVENANCE_FAILED")

    unknowns = set(scope.unresolved) | set(receipt.unresolved)
    if record.status != "SCANNED":
        unknowns.add(f"HU_SOURCE_NOT_SCANNED:{record.status}")
    if verification is None:
        unknowns.add("HU_SOURCE_PROVENANCE_UNVERIFIED")
    else:
        if verification.status != "VERIFIED":
            unknowns.add(f"HU_SOURCE_PROVENANCE_{verification.status}")
        unknowns.update(verification.unverified_properties)
    structural = from_python_ast(target.attributes, evidence_ids=target.evidence_ids)
    if not structural:
        unknowns.add("HU_STRUCTURAL_METRICS_UNAVAILABLE")

    # The adapter transports source facts; only HU computes model indicators.
    # Candidate calls are syntax, never resolved dependencies or navigation cost.
    source_facts = ()
    if (record.status == "SCANNED" and "python_ast" in getattr(record, "collectors", ())
            and hasattr(graph, "edges")):
        calls = tuple(edge for edge in graph.edges
                      if edge.source_id == target_id and edge.relation == "CALLS_CANDIDATE")
        refs = set(target.evidence_ids)
        for edge in calls:
            refs.update(edge.evidence_ids)
        source_facts = (StructuralMetric(
            name="candidate_call_sites", value=len(calls),
            method="python_ast_call_site_v1", evidence_ids=tuple(sorted(refs)),
        ),)

    return evaluate_hu(HUInput(
        target_id=target_id, revision=scope.revision,
        blob_sha=record.blob_sha, structural_metrics=structural,
        observations=observations, unknowns=tuple(sorted(unknowns)),
        source_facts=source_facts,
    ))



def summarize_hu(assessment: HUAssessment):
    """Convert HU evidence to a general analysis record without choosing edits."""
    from .result import AnalysisRecord, AnalysisValue

    if not isinstance(assessment, HUAssessment):
        raise TypeError("HU_ASSESSMENT_REQUIRED")
    values = [AnalysisValue(
        name=f"structural.{metric.name}", value=metric.value,
        method=metric.method, evidence_ids=metric.evidence_ids,
    ) for metric in assessment.structural_metrics]
    for indicator in assessment.indicators:
        values.append(AnalysisValue(
            name=f"indicator.{indicator.name}", value=indicator.value,
            method=indicator.method, evidence_ids=indicator.evidence_ids,
        ))
    for observed in assessment.observed:
        prefix = "observed:" + json.dumps(
            [observed.criterion, observed.question_id],
            separators=(",", ":"), ensure_ascii=False,
        )
        values.extend((
            AnalysisValue(f"{prefix}.positive_count", observed.positive_count, "human_observed"),
            AnalysisValue(f"{prefix}.negative_count", observed.negative_count, "human_observed"),
            AnalysisValue(f"{prefix}.evaluator_count", observed.independent_evaluators, "human_observed"),
        ))
        if observed.positive_rate is not None:
            values.append(AnalysisValue(
                f"{prefix}.positive_rate", observed.positive_rate, "human_observed",
            ))
    refs = tuple(sorted({
        ref for m in (*assessment.structural_metrics, *assessment.indicators)
        for ref in m.evidence_ids
    }))
    return AnalysisRecord(
        name="HU", status="OBSERVED" if assessment.observed else "REVIEW_REQUIRED",
        summary="Source-grounded HU indicators and recorded observations; no verdict"
                if assessment.observed else "Source-grounded HU indicators; no human outcome inferred",
        evidence_ids=refs, source_revision=assessment.revision,
        values=tuple(values), unknowns=assessment.unknowns,
    )


__all__ = ["assess_code_hu", "summarize_hu"]
