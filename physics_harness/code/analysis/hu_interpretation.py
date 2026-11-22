"""Legacy interpretation API. New code uses understandability_interpretation."""

from dataclasses import replace

from .understandability_interpretation import interpret_understandability_indicators


def interpret_hu_indicators(assessment):
    try:
        result = interpret_understandability_indicators(assessment)
    except TypeError as exc:
        if str(exc) == "UNDERSTANDABILITY_ASSESSMENT_REQUIRED":
            raise TypeError("HU_ASSESSMENT_REQUIRED") from exc
        raise
    unknowns = tuple(sorted(
        reason.replace("UNDERSTANDABILITY_IMPROVEMENT_NOT_INFERRED_FROM_INDICATORS",
                       "HU_IMPROVEMENT_NOT_INFERRED_FROM_INDICATORS")
        for reason in result.unknowns
    ))
    return replace(
        result, name="HU_INTERPRETATION", unknowns=unknowns,
        summary=result.summary.replace("code-understandability indicators",
                                       "HU model indicators"),
    )


__all__ = ["interpret_hu_indicators"]
