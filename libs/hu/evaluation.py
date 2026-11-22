"""Legacy human-observation API; generic metrics never require human raters."""

from dataclasses import replace

from libs.code_understandability.evaluation import (
    MetricDifference, UnderstandabilityComparison as HUComparison,
    compare_understandability, evaluate_understandability,
)


def evaluate_hu(sample):
    assessment = evaluate_understandability(sample)
    if sample.observations:
        return assessment
    return replace(assessment, unknowns=tuple(sorted(
        set(assessment.unknowns) | {"HUMAN_UNDERSTANDABILITY_NOT_OBSERVED"}
    )))


def compare_hu(before, after):
    try:
        result = compare_understandability(before, after)
    except ValueError as exc:
        if str(exc) == "UNDERSTANDABILITY_TARGET_MISMATCH":
            raise ValueError("HU_TARGET_MISMATCH") from exc
        raise
    unknowns = tuple(sorted(
        reason.replace("INCOMPARABLE_UNDERSTANDABILITY_", "INCOMPARABLE_HU_")
              .replace("STRUCTURAL_DELTA_NOT_UNDERSTANDABILITY_IMPROVEMENT_PROOF",
                       "STRUCTURAL_DELTA_NOT_HU_IMPROVEMENT_PROOF")
        for reason in result.unknowns
    ))
    return replace(result, unknowns=unknowns)


__all__ = ["HUComparison", "MetricDifference", "compare_hu", "evaluate_hu"]
