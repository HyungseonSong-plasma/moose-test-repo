"""Solver-independent execution IR compiled from ScientificPolicy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionCase:
    case_id: str
    action_id: str
    target: str = ""
    intervention_type: str = ""
    parameters: tuple[tuple[str, Any], ...] = ()
    required_observations: tuple[str, ...] = ()
    held_fixed: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    source_policy_id: str
    cases: tuple[ExecutionCase, ...]
    model_ref: str | None = None
    execution_bounds: tuple[tuple[str, Any], ...] = ()
    required_observations: tuple[str, ...] = ()
    artifact_contracts: tuple[str, ...] = ()
    target_capabilities: tuple[str, ...] = ()
    derived_values: tuple[tuple[str, Any], ...] = ()
    provenance_id: str | None = None

    def case(self, case_id: str) -> ExecutionCase:
        matches = [item for item in self.cases if item.case_id == case_id]
        if len(matches) != 1:
            raise KeyError(f"expected one case {case_id!r}, found {len(matches)}")
        return matches[0]


__all__ = ["ExecutionCase", "ExecutionPlan"]
