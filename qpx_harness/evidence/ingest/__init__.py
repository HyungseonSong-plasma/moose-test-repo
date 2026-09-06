"""Canonical raw-runtime-to-evidence extraction API."""

from .jacobian import extract_jacobian_evidence
from .nonlinear_solver import (
    FAILURE_PATTERNS,
    failure_signature,
)
from .termination import first_failed_reason

__all__ = [
    "FAILURE_PATTERNS",
    "extract_jacobian_evidence",
    "failure_signature",
    "first_failed_reason",
]
