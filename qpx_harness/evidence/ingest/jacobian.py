"""Backend-neutral Jacobian-comparison evidence normalization."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
from typing import Any


def extract_jacobian_evidence(
    comparisons: Iterable[Mapping[str, Any]],
    *,
    provenance: str | None = None,
) -> dict[str, Any]:
    """Summarize already-decoded Jacobian-comparison observations.

    External solver parsers own raw text decoding.  This evidence owner accepts
    canonical comparison records only and deliberately contains no tolerance or
    PASS/HOLD policy.
    """
    tests = [dict(item) for item in comparisons]
    required = {"relative_frobenius_error", "absolute_frobenius_error"}
    for index, item in enumerate(tests):
        missing = required - set(item)
        if missing:
            raise ValueError(
                f"Jacobian comparison {index} missing fields: {sorted(missing)}"
            )

    nonfinite = [
        item
        for item in tests
        if not math.isfinite(float(item["relative_frobenius_error"]))
        or not math.isfinite(float(item["absolute_frobenius_error"]))
    ]
    finite_relative = [
        float(item["relative_frobenius_error"])
        for item in tests
        if math.isfinite(float(item["relative_frobenius_error"]))
    ]
    finite_absolute = [
        float(item["absolute_frobenius_error"])
        for item in tests
        if math.isfinite(float(item["absolute_frobenius_error"]))
    ]
    return {
        "comparison_count": len(tests),
        "tests": tests,
        "provenance": provenance,
        "nonfinite": nonfinite,
        "nonfinite_count": len(nonfinite),
        "worst_relative_frobenius_error": (
            max(finite_relative) if finite_relative else None
        ),
        "worst_absolute_frobenius_error": (
            max(finite_absolute) if finite_absolute else None
        ),
    }


__all__ = ["extract_jacobian_evidence"]
