"""Canonical domain-specific diagnosis presets."""

from .coupled_solver import (
    build_coupled_solver_ruleset,
    coupled_solver_metric_values,
    diagnose_coupled_runtime_evidence,
)
from .green_gauss import build_constant_state_registry, build_constant_state_ruleset
from .jacobian import build_jacobian_ruleset, diagnose_jacobian_evidence

__all__ = [
    "build_constant_state_registry",
    "build_constant_state_ruleset",
    "build_coupled_solver_ruleset",
    "build_jacobian_ruleset",
    "coupled_solver_metric_values",
    "diagnose_coupled_runtime_evidence",
    "diagnose_jacobian_evidence",
]
