"""Context-neutral interpretation of HU model indicators for Refactor Planning.

No metric formula, data transport, fixed threshold, or mutation advice lives here.
"""

from __future__ import annotations

from libs.hu import HUAssessment

from .result import AnalysisRecord, AnalysisValue


def interpret_hu_indicators(assessment: HUAssessment) -> AnalysisRecord:
    """Explain what computed model traits support and what they do not prove."""
    if not isinstance(assessment, HUAssessment):
        raise TypeError("HU_ASSESSMENT_REQUIRED")

    explanations = {
        "branch_density": (
            "branch constructs per source line; not a count of independent responsibilities"
        ),
        "candidate_call_density": (
            "syntactic candidate call sites per source line; not resolved callees"
            " or measured navigation effort"
        ),
    }
    descriptions = [
        f"{metric.name}={metric.value:.6g}: "
        f"{explanations.get(metric.name, 'source-derived feature; impact requires context')}"
        for metric in assessment.indicators
    ]
    if not descriptions:
        descriptions.append("No computable HU model indicators in the source facts")
    descriptions.append("No metric alone proves a change improves human understanding")
    values = tuple(AnalysisValue(
        name=f"indicator.{metric.name}",
        value=metric.value,
        method=metric.method,
        evidence_ids=metric.evidence_ids,
    ) for metric in assessment.indicators)
    evidence_ids = tuple(sorted({
        evidence for metric in assessment.indicators for evidence in metric.evidence_ids
    }))
    unknowns = tuple(sorted(set(assessment.unknowns) | {
        "HU_IMPROVEMENT_NOT_INFERRED_FROM_INDICATORS",
    }))
    return AnalysisRecord(
        name="HU_INTERPRETATION",
        status="REVIEW_REQUIRED",
        summary="; ".join(descriptions),
        evidence_ids=evidence_ids, source_revision=assessment.revision,
        values=values, unknowns=unknowns,
    )


__all__ = ["interpret_hu_indicators"]
