"""Generic deterministic comparison of named scalar fields."""
from __future__ import annotations

import math
from collections.abc import Mapping


def compare_named_scalars(
    candidate: Mapping[str, float],
    reference: Mapping[str, float],
    *,
    relative_tolerance: float,
    absolute_tolerance: float = 0.0,
) -> dict[str, object]:
    """Compare two named scalar mappings with explicit tolerances.

    This capability contains no D_mix, species, campaign, solver, or Issue
    semantics.  Callers retain provenance and scientific acceptance policy.
    """
    if not math.isfinite(relative_tolerance) or relative_tolerance < 0.0:
        raise ValueError("relative_tolerance must be finite and non-negative")
    if not math.isfinite(absolute_tolerance) or absolute_tolerance < 0.0:
        raise ValueError("absolute_tolerance must be finite and non-negative")
    candidate_keys = set(candidate)
    reference_keys = set(reference)
    if candidate_keys != reference_keys:
        return {
            "status": "FAIL",
            "missing_in_candidate": sorted(reference_keys - candidate_keys),
            "missing_in_reference": sorted(candidate_keys - reference_keys),
        }

    rows: dict[str, dict[str, float | bool]] = {}
    max_relative_error = 0.0
    max_absolute_error = 0.0
    passed = True
    for key in sorted(candidate_keys):
        actual = float(candidate[key])
        expected = float(reference[key])
        if not math.isfinite(actual) or not math.isfinite(expected):
            rows[key] = {
                "candidate": actual,
                "reference": expected,
                "absolute_error": math.inf,
                "relative_error": math.inf,
                "passed": False,
            }
            passed = False
            max_relative_error = math.inf
            max_absolute_error = math.inf
            continue
        absolute_error = abs(actual - expected)
        scale = max(abs(actual), abs(expected))
        relative_error = absolute_error / scale if scale else 0.0
        row_passed = (
            absolute_error <= absolute_tolerance
            or relative_error <= relative_tolerance
        )
        rows[key] = {
            "candidate": actual,
            "reference": expected,
            "absolute_error": absolute_error,
            "relative_error": relative_error,
            "passed": row_passed,
        }
        max_relative_error = max(max_relative_error, relative_error)
        max_absolute_error = max(max_absolute_error, absolute_error)
        passed = passed and row_passed

    return {
        "status": "PASS" if passed else "FAIL",
        "max_relative_error": max_relative_error,
        "max_absolute_error": max_absolute_error,
        "rows": rows,
    }


__all__ = ["compare_named_scalars"]
