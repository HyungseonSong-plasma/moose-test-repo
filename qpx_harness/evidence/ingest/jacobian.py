"""PETSc Jacobian comparison facts with no tolerance or diagnosis policy."""
from __future__ import annotations

import math
from typing import Any

from ...petsc import jacobian as petsc_jacobian


def extract_jacobian_evidence(text: str) -> dict[str, Any]:
    """Parse and summarize observable PETSc Jacobian-comparison facts.

    This function deliberately does not decide PASS/HOLD or compare against a
    scientific tolerance. Those decisions belong to :mod:`qpx_harness.diagnose`.
    """
    tests = petsc_jacobian.parse_comparisons(text)
    nonfinite = [
        item
        for item in tests
        if not math.isfinite(item["relative_frobenius_error"])
        or not math.isfinite(item["absolute_frobenius_error"])
    ]
    finite_relative = [
        float(item["relative_frobenius_error"])
        for item in tests
        if math.isfinite(item["relative_frobenius_error"])
    ]
    finite_absolute = [
        float(item["absolute_frobenius_error"])
        for item in tests
        if math.isfinite(item["absolute_frobenius_error"])
    ]
    return {
        "comparison_count": len(tests),
        "tests": tests,
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
