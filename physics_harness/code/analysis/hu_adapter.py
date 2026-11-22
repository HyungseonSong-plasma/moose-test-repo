"""Legacy adapter API. New code uses understandability_adapter."""

from dataclasses import replace

from .understandability_adapter import (
    assess_code_understandability, summarize_understandability,
)


def assess_code_hu(diagnostic, target_id, *, observations=()):
    result = assess_code_understandability(
        diagnostic, target_id, observations=observations,
    )
    if observations:
        return result
    return replace(result, unknowns=tuple(sorted(
        set(result.unknowns) | {"HUMAN_UNDERSTANDABILITY_NOT_OBSERVED"}
    )))


def summarize_hu(assessment):
    result = summarize_understandability(assessment)
    return replace(
        result,
        name="HU",
        status="OBSERVED" if assessment.observed else "REVIEW_REQUIRED",
        summary=("Source-grounded HU indicators and recorded observations; no verdict"
                 if assessment.observed else
                 "Source-grounded HU indicators; no human outcome inferred"),
    )


__all__ = ["assess_code_hu", "summarize_hu"]
