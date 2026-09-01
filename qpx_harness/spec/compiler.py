"""Deterministic ExperimentSpec v1 -> ExecutionPlan compiler."""
from __future__ import annotations

from .errors import ExperimentSpecError, SpecProblem
from .models import (
    AddPetscFlagsOperation,
    CaseSpec,
    EnsureBlockOperation,
    ExperimentSpec,
    InsertChildBlockOperation,
    InsertTopLevelBeforeOperation,
    RemoveBlockOperation,
    RemovePathsOperation,
    RemovePetscFlagsOperation,
    RemovePetscOptionOperation,
    ReplaceBlockOperation,
    SetParameterOperation,
    SetPetscOptionOperation,
)
from .plan import CasePlan, ExecutionPlan, OperationPlan


def _compile_operation(operation: object) -> OperationPlan:
    if isinstance(operation, EnsureBlockOperation):
        return OperationPlan(
            op="ensure_block",
            arguments=(("path", operation.path), ("block", operation.block)),
        )
    if isinstance(operation, SetParameterOperation):
        return OperationPlan(
            op="set_parameter",
            arguments=(
                ("path", operation.path),
                ("name", operation.name),
                ("value", operation.value),
            ),
        )
    if isinstance(operation, AddPetscFlagsOperation):
        return OperationPlan(
            op="add_petsc_flags",
            arguments=(
                ("flags", tuple(operation.flags)),
                ("path", operation.path),
                ("parameter", operation.parameter),
            ),
        )
    if isinstance(operation, RemoveBlockOperation):
        return OperationPlan(op="remove_block", arguments=(("path", operation.path),))
    if isinstance(operation, ReplaceBlockOperation):
        return OperationPlan(
            op="replace_block",
            arguments=(("path", operation.path), ("block", operation.block)),
        )
    if isinstance(operation, InsertChildBlockOperation):
        return OperationPlan(
            op="insert_child_block",
            arguments=(
                ("parent", operation.parent),
                ("path", operation.path),
                ("block", operation.block),
            ),
        )
    if isinstance(operation, InsertTopLevelBeforeOperation):
        return OperationPlan(
            op="insert_top_level_before",
            arguments=(("marker", operation.marker), ("block", operation.block)),
        )
    if isinstance(operation, RemovePathsOperation):
        return OperationPlan(
            op="remove_paths",
            arguments=(("paths", tuple(operation.paths)),),
        )
    if isinstance(operation, RemovePetscFlagsOperation):
        return OperationPlan(
            op="remove_petsc_flags",
            arguments=(
                ("flags", tuple(operation.flags)),
                ("path", operation.path),
                ("parameter", operation.parameter),
            ),
        )
    if isinstance(operation, SetPetscOptionOperation):
        return OperationPlan(
            op="set_petsc_option",
            arguments=(
                ("name", operation.name),
                ("value", operation.value),
                ("path", operation.path),
                ("names_parameter", operation.names_parameter),
                ("values_parameter", operation.values_parameter),
            ),
        )
    if isinstance(operation, RemovePetscOptionOperation):
        return OperationPlan(
            op="remove_petsc_option",
            arguments=(
                ("name", operation.name),
                ("path", operation.path),
                ("names_parameter", operation.names_parameter),
                ("values_parameter", operation.values_parameter),
            ),
        )
    raise ExperimentSpecError(
        (
            SpecProblem(
                code="SPEC_UNKNOWN_OPERATION",
                message=f"unsupported operation model: {type(operation).__name__}",
            ),
        )
    )


def _compile_case(case: CaseSpec) -> CasePlan:
    return CasePlan(
        case_id=case.case_id,
        operations=tuple(_compile_operation(operation) for operation in case.operations),
    )


def compile_spec(spec: ExperimentSpec) -> ExecutionPlan:
    case_ids = [case.case_id for case in spec.cases]
    duplicates = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
    if duplicates:
        raise ExperimentSpecError(
            (
                SpecProblem(
                    code="SPEC_DUPLICATE_CASE_ID",
                    message="duplicate case_id values: " + ", ".join(duplicates),
                ),
            )
        )
    return ExecutionPlan(
        schema_version=spec.schema_version,
        experiment_id=spec.experiment_id,
        description=spec.description,
        cases=tuple(_compile_case(case) for case in spec.cases),
    )
