"""Reusable numerical/runtime diagnostic facts with no issue-specific policy."""

from .jacobian import analyze_comparisons
from .nonlinear_solver import (
    failure_signature,
    measurement_failure_signature,
    runtime_core_facts,
)
from .termination import first_failed_reason, first_linear_termination

__all__ = [
    "analyze_comparisons",
    "first_failed_reason",
    "first_linear_termination",
    "failure_signature",
    "measurement_failure_signature",
    "runtime_core_facts",
]
