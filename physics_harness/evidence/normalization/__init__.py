"""Canonical backend-neutral evidence normalization."""

from .jacobian import extract_jacobian_evidence
from .termination import first_failed_reason

__all__ = [
    "extract_jacobian_evidence",
    "first_failed_reason",
]
