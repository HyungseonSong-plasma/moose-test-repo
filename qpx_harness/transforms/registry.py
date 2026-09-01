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


def _string_tuple_argument(operation: OperationPlan, name: str) -> tuple[str, ...]:
    value = operation.argument_dict().get(name)
    if not isinstance(value, tuple) or not value or not all(isinstance(item, str) and item for item in value):
        raise TransformError(f"{operation.op} requires non-empty tuple[str, ...] argument {name!r}")
    return value


def _ensure_block(text: str, operation: OperationPlan) -> str:
    path = _string_argument(operation, "path")
    block = _string_argument(operation, "block")
    try:
        matches = MooseInput(text).find(path)
        if len(matches) > 1:
            raise TransformError(f"multiple blocks already match {path!r}")
        if len(matches) == 1:
            return text
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
    flags = _string_tuple_argument(operation, "flags")
    path = _string_argument(operation, "path")
    parameter = _string_argument(operation, "parameter")
    try:
        return petsc_options.add_flags(text, flags, path=path, parameter=parameter)
    except (petsc_options.PetscOptionsError, moose_parameters.MooseParameterError) as exc:
        raise TransformError(str(exc)) from exc


def _remove_block(text: str, operation: OperationPlan) -> str:
    path = _string_argument(operation, "path")
    try:
        return moose_blocks.remove_block(text, path)
    except (moose_blocks.MooseBlockError, MooseInputError) as exc:
        raise TransformError(str(exc)) from exc


def _replace_block(text: str, operation: OperationPlan) -> str:
    path = _string_argument(operation, "path")
    block = _string_argument(operation, "block")
    try:
        return moose_blocks.replace_block(text, path, block)
    except (moose_blocks.MooseBlockError, MooseInputError) as exc:
        raise TransformError(str(exc)) from exc


def _insert_child_block(text: str, operation: OperationPlan) -> str:
    parent = _string_argument(operation, "parent")
    path = _string_argument(operation, "path")
    block = _string_argument(operation, "block")
    try:
        if moose_blocks.has_block(text, path):
            raise TransformError(f"insert_child_block target already exists: {path!r}")
        out = moose_blocks.insert_child_block(text, parent, block)
        if not moose_blocks.has_block(out, path):
            raise TransformError(f"insert_child_block did not create {path!r}")
        return out
    except (moose_blocks.MooseBlockError, MooseInputError) as exc:
        raise TransformError(str(exc)) from exc


def _insert_top_level_before(text: str, operation: OperationPlan) -> str:
    marker = _string_argument(operation, "marker")
    block = _string_argument(operation, "block")
    marker_path = marker.strip("/")
    if "/" in marker_path:
        raise TransformError("insert_top_level_before marker must be top-level")
    try:
        matches = MooseInput(text).find(marker_path)
    except MooseInputError as exc:
        raise TransformError(str(exc)) from exc
    if len(matches) != 1:
        raise TransformError(
            f"insert_top_level_before expected one marker {marker_path!r}, found {len(matches)}"
        )
    needle = f"\n[{marker_path}]\n"
    if text.count(needle) != 1:
        raise TransformError(
            f"insert_top_level_before requires one canonical marker line for {marker_path!r}"
        )
    payload = block if block.endswith("\n") else block + "\n"
    return text.replace(needle, "\n" + payload + needle, 1)


def _remove_paths(text: str, operation: OperationPlan) -> str:
    paths = _string_tuple_argument(operation, "paths")
    try:
        out, _ = MooseInput(text).remove_paths(paths)
        return out
    except MooseInputError as exc:
        raise TransformError(str(exc)) from exc


def _remove_petsc_flags(text: str, operation: OperationPlan) -> str:
    flags = _string_tuple_argument(operation, "flags")
    path = _string_argument(operation, "path")
    parameter = _string_argument(operation, "parameter")
    try:
        return petsc_options.remove_flags(text, flags, path=path, parameter=parameter)
    except (petsc_options.PetscOptionsError, moose_parameters.MooseParameterError) as exc:
        raise TransformError(str(exc)) from exc


def _set_petsc_option(text: str, operation: OperationPlan) -> str:
    name = _string_argument(operation, "name")
    value = _string_argument(operation, "value")
    path = _string_argument(operation, "path")
    names_parameter = _string_argument(operation, "names_parameter")
    values_parameter = _string_argument(operation, "values_parameter")
    try:
        return petsc_options.upsert_name_value(
            text,
            name,
            value,
            path=path,
            names_parameter=names_parameter,
            values_parameter=values_parameter,
        )
    except (petsc_options.PetscOptionsError, moose_parameters.MooseParameterError) as exc:
        raise TransformError(str(exc)) from exc


def _remove_petsc_option(text: str, operation: OperationPlan) -> str:
    name = _string_argument(operation, "name")
    path = _string_argument(operation, "path")
    names_parameter = _string_argument(operation, "names_parameter")
    values_parameter = _string_argument(operation, "values_parameter")
    try:
        return petsc_options.remove_name_value(
            text,
            name,
            path=path,
            names_parameter=names_parameter,
            values_parameter=values_parameter,
        )
    except (petsc_options.PetscOptionsError, moose_parameters.MooseParameterError) as exc:
        raise TransformError(str(exc)) from exc


_REGISTRY: dict[str, Transform] = {
    "ensure_block": _ensure_block,
    "set_parameter": _set_parameter,
    "add_petsc_flags": _add_petsc_flags,
    "remove_block": _remove_block,
    "replace_block": _replace_block,
    "insert_child_block": _insert_child_block,
    "insert_top_level_before": _insert_top_level_before,
    "remove_paths": _remove_paths,
    "remove_petsc_flags": _remove_petsc_flags,
    "set_petsc_option": _set_petsc_option,
    "remove_petsc_option": _remove_petsc_option,
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
