"""Context-neutral interpretation of code-understandability indicators for Refactor Planning.

No metric formula, data transport, fixed threshold, or mutation advice lives here.
"""

from __future__ import annotations

from libs.code_lucidity import UnderstandabilityAssessment

from ..result import AnalysisRecord, AnalysisValue


def interpret_understandability_indicators(assessment: UnderstandabilityAssessment) -> AnalysisRecord:
    """Explain what computed model traits support and what they do not prove."""
    if not isinstance(assessment, UnderstandabilityAssessment):
        raise TypeError("UNDERSTANDABILITY_ASSESSMENT_REQUIRED")

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
        descriptions.append("No computable code-understandability indicators in the source facts")
    descriptions.append("No metric alone proves a change improves code understandability")
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
        "UNDERSTANDABILITY_IMPROVEMENT_NOT_INFERRED_FROM_INDICATORS",
    }))
    return AnalysisRecord(
        name="CODE_UNDERSTANDABILITY_INTERPRETATION",
        status="REVIEW_REQUIRED",
        summary="; ".join(descriptions),
        evidence_ids=evidence_ids, source_revision=assessment.revision,
        values=values, unknowns=unknowns,
    )


__all__ = ["interpret_understandability_indicators"]
