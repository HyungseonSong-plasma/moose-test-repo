"""Bounded generic transform registry for ExperimentSpec v1 plans."""
from __future__ import annotations

from collections.abc import Callable

from ..moose import blocks as moose_blocks
from ..moose import parameters as moose_parameters
from ..moose_input import MooseInput, MooseInputError
from ..petsc import options as petsc_options
from ..spec.plan import CasePlan, OperationPlan


class TransformError(RuntimeError):
    """Raised when a generic declarative transform cannot be applied."""


Transform = Callable[[str, OperationPlan], str]


def _string_argument(operation: OperationPlan, name: str) -> str:
    value = operation.argument_dict().get(name)
    if not isinstance(value, str):
        raise TransformError(f"{operation.op} requires string argument {name!r}")
    return value


def _ensure_block(text: str, operation: OperationPlan) -> str:
    path = _string_argument(operation, "path")
    block = _string_argument(operation, "block")
    matches = MooseInput(text).find(path)
    if len(matches) > 1:
        raise TransformError(f"multiple blocks already match {path!r}")
    if len(matches) == 1:
        return text

    try:
        if "/" in path:
            parent = path.rsplit("/", 1)[0]
            out = moose_blocks.insert_child_block(text, parent, block)
        else:
            out = moose_blocks.append_top_level_block(text, block)
        matches = MooseInput(out).find(path)
    except (MooseInputError, moose_blocks.MooseBlockError) as exc:
        raise TransformError(str(exc)) from exc
    if len(matches) != 1:
        raise TransformError(
            f"ensure_block payload did not create exactly one block {path!r}"
        )
    return out


def _set_parameter(text: str, operation: OperationPlan) -> str:
    path = _string_argument(operation, "path")
    name = _string_argument(operation, "name")
    value = _string_argument(operation, "value")
    try:
        return moose_parameters.upsert_parameter(text, path, name, value)
    except moose_parameters.MooseParameterError as exc:
        raise TransformError(str(exc)) from exc


def _add_petsc_flags(text: str, operation: OperationPlan) -> str:
    args = operation.argument_dict()
    flags = args.get("flags")
    path = args.get("path")
    parameter = args.get("parameter")
    if not isinstance(flags, tuple) or not all(isinstance(flag, str) for flag in flags):
        raise TransformError("add_petsc_flags requires tuple[str, ...] argument 'flags'")
    if not isinstance(path, str) or not isinstance(parameter, str):
        raise TransformError("add_petsc_flags path/parameter must be strings")
    try:
        return petsc_options.add_flags(
            text,
            flags,
            path=path,
            parameter=parameter,
        )
    except (petsc_options.PetscOptionsError, moose_parameters.MooseParameterError) as exc:
        raise TransformError(str(exc)) from exc


_REGISTRY: dict[str, Transform] = {
    "ensure_block": _ensure_block,
    "set_parameter": _set_parameter,
    "add_petsc_flags": _add_petsc_flags,
}

SUPPORTED_OPERATIONS = frozenset(_REGISTRY)


def apply_operation(text: str, operation: OperationPlan) -> str:
    transform = _REGISTRY.get(operation.op)
    if transform is None:
        raise TransformError(f"unknown transform operation: {operation.op}")
    return transform(text, operation)


def apply_case_plan(text: str, case: CasePlan) -> str:
    out = text
    for operation in case.operations:
        out = apply_operation(out, operation)
    return out
