"""Validation-facing exports for canonical Jacobian reasoning."""
from qpx_harness.reasoning.jacobian import (
    build_jacobian_ruleset,
    diagnose_jacobian_evidence,
)

__all__ = ["build_jacobian_ruleset", "diagnose_jacobian_evidence"]
