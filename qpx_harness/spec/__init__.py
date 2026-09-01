"""Declarative ExperimentSpec v1 schema and deterministic planning."""
from .compiler import compile_spec
from .errors import (
    ExperimentSpecDependencyError,
    ExperimentSpecError,
    SpecProblem,
)
from .loader import load_json_file, load_json_text, load_payload
from .models import (
    AddPetscFlagsOperation,
    CaseSpec,
    EnsureBlockOperation,
    ExperimentSpec,
    SetParameterOperation,
    pydantic_major_api,
)
from .plan import CasePlan, ExecutionPlan, OperationPlan

__all__ = [
    "AddPetscFlagsOperation",
    "CasePlan",
    "CaseSpec",
    "EnsureBlockOperation",
    "ExecutionPlan",
    "ExperimentSpec",
    "ExperimentSpecDependencyError",
    "ExperimentSpecError",
    "OperationPlan",
    "SetParameterOperation",
    "SpecProblem",
    "compile_spec",
    "load_json_file",
    "load_json_text",
    "load_payload",
    "pydantic_major_api",
]
