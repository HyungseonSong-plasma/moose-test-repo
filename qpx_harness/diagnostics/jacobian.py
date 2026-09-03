"""Compatibility API for Jacobian analysis via Evidence -> Diagnose."""
from __future__ import annotations

from typing import Any

from qpx_harness.diagnose import diagnose_jacobian_evidence
from qpx_harness.evidence import extract_jacobian_evidence


def analyze_comparisons(text: str, *, relative_tolerance: float) -> dict[str, Any]:
    evidence = extract_jacobian_evidence(text)
    return diagnose_jacobian_evidence(
        evidence,
        relative_tolerance=relative_tolerance,
    )


__all__ = ["analyze_comparisons"]
