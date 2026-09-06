"""Reusable MOOSE/PETSc runtime evidence extraction with no diagnosis policy."""
from __future__ import annotations

import re
from typing import Any

from ...moose import log as moose_log
from ...petsc import log as petsc_log
from .termination import first_failed_reason


FAILURE_PATTERNS = (
    ("DIVERGED_MAX_IT", r"DIVERGED_MAX_IT(?:\s+iterations\s+(\d+))?"),
    ("DIVERGED_LINE_SEARCH", r"DIVERGED_LINE_SEARCH"),
    ("DIVERGED_FNORM_NAN", r"DIVERGED_FNORM_NAN|NaN"),
    (
        "NONLINEAR_DID_NOT_CONVERGE",
        r"Nonlinear solve did not converge|Solve Did NOT Converge",
    ),
)


def failure_signature(text: str) -> dict[str, Any]:
    """Extract the first stable nonlinear-failure signature from runtime text."""
    for name, pattern in FAILURE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        iterations = None
        if match.lastindex and match.group(1):
            try:
                iterations = int(match.group(1))
            except ValueError:
                pass
        return {"signature": name, "iterations": iterations}
    return {"signature": None, "iterations": None}



__all__ = ["FAILURE_PATTERNS", "failure_signature"]
