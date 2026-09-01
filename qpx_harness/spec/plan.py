"""Immutable intermediate representation for compiled ExperimentSpec data."""
from __future__ import annotations

from dataclasses import dataclass


PlanValue = str | int | float | bool | None | tuple[str, ...]


@dataclass(frozen=True)
class OperationPlan:
    op: str
    arguments: tuple[tuple[str, PlanValue], ...] = ()

    def argument_dict(self) -> dict[str, PlanValue]:
        return dict(self.arguments)


@dataclass(frozen=True)
class CasePlan:
    case_id: str
    operations: tuple[OperationPlan, ...]


@dataclass(frozen=True)
class ExecutionPlan:
    schema_version: int
    experiment_id: str
    description: str | None
    cases: tuple[CasePlan, ...]

    def case(self, case_id: str) -> CasePlan:
        matches = [case for case in self.cases if case.case_id == case_id]
        if len(matches) != 1:
            raise KeyError(f"expected one case {case_id!r}, found {len(matches)}")
        return matches[0]
