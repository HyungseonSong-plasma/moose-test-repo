"""MOOSE target realization boundary for solver-independent ExecutionPlan.

This adapter owns MOOSE spelling only.  Scientific meaning remains upstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from qpx_harness.execution.plan import ExecutionCase, ExecutionPlan


class MooseLoweringError(ValueError):
    pass


@dataclass(frozen=True)
class MooseAssignment:
    path: str
    name: str
    value: str


@dataclass(frozen=True)
class MooseBlock:
    path: str
    type_name: str | None = None
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MooseCaseIR:
    case_id: str
    action_id: str
    blocks: tuple[MooseBlock, ...] = ()
    assignments: tuple[MooseAssignment, ...] = ()
    required_observations: tuple[str, ...] = ()


@dataclass(frozen=True)
class MooseTargetIR:
    source_plan_id: str
    cases: tuple[MooseCaseIR, ...]
    execution_bounds: tuple[tuple[str, Any], ...] = ()


CaseLowerer = Callable[[ExecutionCase], MooseCaseIR]


def _default_case_lowerer(case: ExecutionCase) -> MooseCaseIR:
    """Target-neutral fallback represented as MOOSE adapter metadata only.

    A scientific capability requiring concrete MOOSE objects must register an
    explicit target lowerer.  The fallback never guesses physics object names.
    """
    return MooseCaseIR(
        case_id=case.case_id,
        action_id=case.action_id,
        assignments=tuple(
            MooseAssignment(path="QPX/Parameters", name=name, value=str(value))
            for name, value in case.parameters
        ),
        required_observations=case.required_observations,
    )


def lower_execution_plan(
    plan: ExecutionPlan,
    *,
    lowerers: Mapping[str, CaseLowerer] | None = None,
) -> MooseTargetIR:
    """Lower an ExecutionPlan into structured target IR deterministically.

    `lowerers` are keyed by ActionSpec identity or an application-defined stable
    action class.  No Issue-number dispatch is performed here.
    """
    lowerers = dict(lowerers or {})
    cases: list[MooseCaseIR] = []
    for case in plan.cases:
        lowerer = lowerers.get(case.action_id, _default_case_lowerer)
        lowered = lowerer(case)
        if lowered.case_id != case.case_id or lowered.action_id != case.action_id:
            raise MooseLoweringError("target lowerer changed case/action identity")
        cases.append(lowered)
    return MooseTargetIR(
        source_plan_id=plan.plan_id,
        cases=tuple(cases),
        execution_bounds=plan.execution_bounds,
    )


def emit_moose_input(case: MooseCaseIR) -> str:
    """Emit deterministic MOOSE-style target text from structured IR.

    The emitted form is intentionally mechanical.  Scientific target mappings
    must have been decided by the lowerer that created the IR.
    """
    lines: list[str] = [
        f"# QPX case_id: {case.case_id}",
        f"# QPX action_id: {case.action_id}",
    ]
    for block in sorted(case.blocks, key=lambda item: item.path):
        lines.append(f"[{block.path}]")
        if block.type_name is not None:
            lines.append(f"  type = {block.type_name}")
        for name, value in sorted(block.parameters):
            lines.append(f"  {name} = {value}")
        lines.append("[]")
    if case.assignments:
        lines.append("[QPX]")
        for assignment in sorted(case.assignments, key=lambda item: (item.path, item.name)):
            safe_path = assignment.path.replace("/", "__")
            lines.append(f"  {safe_path}__{assignment.name} = {assignment.value}")
        lines.append("[]")
    for observation in sorted(case.required_observations):
        lines.append(f"# QPX observation: {observation}")
    return "\n".join(lines) + "\n"


__all__ = [
    "MooseAssignment", "MooseBlock", "MooseCaseIR", "MooseTargetIR",
    "MooseLoweringError", "lower_execution_plan", "emit_moose_input",
]
