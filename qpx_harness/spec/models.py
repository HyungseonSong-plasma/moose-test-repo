"""Strict, versioned Pydantic models for ExperimentSpec v1."""
from __future__ import annotations

from typing import Any, Literal, Union

from .errors import ExperimentSpecDependencyError

try:
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - environment contract
    raise ExperimentSpecDependencyError(
        "ExperimentSpec v1 requires the 'pydantic' package"
    ) from exc

_PYDANTIC_V2 = hasattr(BaseModel, "model_validate")

if _PYDANTIC_V2:
    from pydantic import ConfigDict

    class StrictModel(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

else:  # pragma: no cover - exercised only on Pydantic v1

    class StrictModel(BaseModel):
        class Config:
            extra = "forbid"
            allow_mutation = False


class EnsureBlockOperation(StrictModel):
    op: Literal["ensure_block"]
    path: str = Field(min_length=1)
    block: str = Field(min_length=1)


class SetParameterOperation(StrictModel):
    op: Literal["set_parameter"]
    path: str = Field(min_length=1)
    name: str = Field(min_length=1)
    value: str


class AddPetscFlagsOperation(StrictModel):
    op: Literal["add_petsc_flags"]
    flags: tuple[str, ...] = Field(min_length=1)
    path: str = "Executioner"
    parameter: str = "petsc_options"


OperationSpec = Union[
    EnsureBlockOperation,
    SetParameterOperation,
    AddPetscFlagsOperation,
]


class CaseSpec(StrictModel):
    case_id: str = Field(min_length=1)
    operations: tuple[OperationSpec, ...] = ()


class ExperimentSpec(StrictModel):
    schema_version: Literal[1]
    experiment_id: str = Field(min_length=1)
    description: str | None = None
    cases: tuple[CaseSpec, ...] = Field(min_length=1)


def model_validate(payload: Any) -> ExperimentSpec:
    """Validate one payload on either supported Pydantic major API."""
    if _PYDANTIC_V2:
        return ExperimentSpec.model_validate(payload)
    return ExperimentSpec.parse_obj(payload)


def model_dump(model: BaseModel) -> dict[str, Any]:
    """Return Python-native model data independent of Pydantic major API."""
    if _PYDANTIC_V2:
        return model.model_dump(mode="python")
    return model.dict()


def pydantic_major_api() -> str:
    return "v2" if _PYDANTIC_V2 else "v1"
