"""Reusable assembled-vs-finite-difference Jacobian comparison facts."""
from __future__ import annotations

import math
from typing import Any

from ..petsc import jacobian as petsc_jacobian


def analyze_comparisons(text: str, *, relative_tolerance: float) -> dict[str, Any]:
    """Classify PETSc Jacobian-comparison output against a caller-owned tolerance.

    The tolerance is supplied by the scientific/experiment owner. This capability
    owns only the invariant parsing and finite/error comparison mechanics.
    """
    tests = petsc_jacobian.parse_comparisons(text)
    if not tests:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_EVIDENCE_INSUFFICIENT",
            "reason": "PETSc -snes_test_jacobian produced no parseable Jacobian comparison",
            "relative_tolerance": relative_tolerance,
            "tests": [],
        }

    nonfinite = [
        item
        for item in tests
        if not math.isfinite(item["relative_frobenius_error"])
        or not math.isfinite(item["absolute_frobenius_error"])
    ]
    finite_rel = [
        item["relative_frobenius_error"]
        for item in tests
        if math.isfinite(item["relative_frobenius_error"])
    ]
    worst = max(finite_rel) if finite_rel else math.inf
    if nonfinite or worst > relative_tolerance:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_MISMATCH",
            "reason": (
                "assembled-vs-finite-difference Jacobian relative Frobenius error exceeds "
                f"the declared tolerance {relative_tolerance:g} or is non-finite"
            ),
            "relative_tolerance": relative_tolerance,
            "worst_relative_frobenius_error": worst,
            "nonfinite": nonfinite,
            "tests": tests,
        }
    return {
        "status": "PASS",
        "class": "JACOBIAN_CORRECTNESS_PASS",
        "reason": "all observed PETSc Jacobian comparisons satisfy the declared relative tolerance",
        "relative_tolerance": relative_tolerance,
        "worst_relative_frobenius_error": worst,
        "nonfinite": [],
        "tests": tests,
    }
