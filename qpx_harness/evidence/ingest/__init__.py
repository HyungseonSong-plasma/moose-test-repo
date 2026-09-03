"""Canonical raw-runtime-to-evidence extraction API."""

from .jacobian import extract_jacobian_evidence
from .nonlinear_solver import (
    FAILURE_PATTERNS,
    failure_signature,
    measurement_failure_signature,
    runtime_core_facts,
)
from .termination import first_failed_reason, first_linear_termination

__all__ = [
    "FAILURE_PATTERNS",
    "extract_jacobian_evidence",
    "failure_signature",
    "first_failed_reason",
    "first_linear_termination",
    "measurement_failure_signature",
    "runtime_core_facts",
]
