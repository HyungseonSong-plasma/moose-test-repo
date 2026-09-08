"""Canonical declarative QPX Experiment Specification.

The schema describes scientific intent and deliberately excludes target-solver
mutation operations.  Closed-world validation happens before semantic compilation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 2
_ALLOWED_ROOT_FIELDS = {
    "schema_version", "experiment_id", "description", "objective", "model_ref",
    "target_claims", "target_questions", "requested_capabilities", "parameters",
    "constraints", "observations", "execution_bounds", "cases", "provenance",
}
_FORBIDDEN_TARGET_FIELDS = {
    "ensure_block", "set_parameter", "replace_block", "insert_child_block",
    "insert_top_level_before", "remove_paths", "add_petsc_flags",
    "remove_petsc_flags", "set_petsc_option", "remove_petsc_option",
}


class ExperimentSpecError(ValueError):
    code = "SPEC_SCHEMA_ERROR"


class SpecSemanticError(ExperimentSpecError):
    code = "SPEC_SEMANTIC_ERROR"


class UnsupportedCapabilityError(SpecSemanticError):
    code = "UNSUPPORTED_CAPABILITY"


@dataclass(frozen=True)
class CaseDeclaration:
    case_id: str
    parameters: tuple[tuple[str, Any], ...] = ()
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExperimentSpec:
    schema_version: int
    experiment_id: str
    objective: str
    source_path: Path
    description: str | None = None
    model_ref: str | None = None
    target_claims: tuple[str, ...] = ()
    target_questions: tuple[str, ...] = ()
    requested_capabilities: tuple[str, ...] = ()
    parameters: tuple[tuple[str, Any], ...] = ()
    constraints: tuple[str, ...] = ()
    observations: tuple[str, ...] = ()
    execution_bounds: tuple[tuple[str, Any], ...] = ()
    cases: tuple[CaseDeclaration, ...] = ()
    provenance: tuple[tuple[str, str], ...] = ()


def _require_string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ExperimentSpecError(f"{name} must be a non-empty string")
    return value.strip()


def _strings(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ExperimentSpecError(f"{name} must be an array of non-empty strings")
    return tuple(item.strip() for item in value)


def _mapping_items(value: Any, name: str) -> tuple[tuple[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ExperimentSpecError(f"{name} must be an object")
    return tuple(sorted(value.items(), key=lambda item: item[0]))


def _reject_target_syntax(value: Any, path: str = "$.") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _FORBIDDEN_TARGET_FIELDS or key in {"FVKernels", "FunctorMaterials", "Executioner"}:
                raise SpecSemanticError(
                    f"target-solver mutation field {key!r} is not part of canonical ExperimentSpec ({path})"
                )
            _reject_target_syntax(child, f"{path}{key}.")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_target_syntax(child, f"{path}[{index}].")


def _parse_cases(value: Any) -> tuple[CaseDeclaration, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ExperimentSpecError("cases must be an array")
    result: list[CaseDeclaration] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ExperimentSpecError("each case must be an object")
        unknown = set(raw) - {"case_id", "parameters", "constraints"}
        if unknown:
            raise ExperimentSpecError(f"unknown case fields: {sorted(unknown)}")
        case_id = _require_string(raw, "case_id")
        if case_id in seen:
            raise ExperimentSpecError(f"duplicate case identity: {case_id}")
        seen.add(case_id)
        result.append(
            CaseDeclaration(
                case_id=case_id,
                parameters=_mapping_items(raw.get("parameters"), "case.parameters"),
                constraints=_strings(raw.get("constraints"), "case.constraints"),
            )
        )
    return tuple(result)


def validate_payload(payload: Any, *, source_path: Path) -> ExperimentSpec:
    if not isinstance(payload, dict):
        raise ExperimentSpecError("experiment specification root must be an object")
    unknown = set(payload) - _ALLOWED_ROOT_FIELDS
    if unknown:
        raise ExperimentSpecError(f"unknown ExperimentSpec fields: {sorted(unknown)}")
    _reject_target_syntax(payload)
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ExperimentSpecError(
            f"unsupported schema_version {version!r}; expected {SCHEMA_VERSION}"
        )
    objective = payload.get("objective") or payload.get("description")
    if not isinstance(objective, str) or not objective.strip():
        raise ExperimentSpecError("objective must be a non-empty string")
    model_ref = payload.get("model_ref")
    if model_ref is not None and (not isinstance(model_ref, str) or not model_ref.strip()):
        raise ExperimentSpecError("model_ref must be a non-empty string when provided")
    provenance_raw = payload.get("provenance")
    if provenance_raw is not None:
        if not isinstance(provenance_raw, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in provenance_raw.items()):
            raise ExperimentSpecError("provenance must be an object of string values")
    return ExperimentSpec(
        schema_version=SCHEMA_VERSION,
        experiment_id=_require_string(payload, "experiment_id"),
        objective=objective.strip(),
        source_path=source_path,
        description=payload.get("description") if isinstance(payload.get("description"), str) else None,
        model_ref=model_ref.strip() if isinstance(model_ref, str) else None,
        target_claims=_strings(payload.get("target_claims"), "target_claims"),
        target_questions=_strings(payload.get("target_questions"), "target_questions"),
        requested_capabilities=_strings(payload.get("requested_capabilities"), "requested_capabilities"),
        parameters=_mapping_items(payload.get("parameters"), "parameters"),
        constraints=_strings(payload.get("constraints"), "constraints"),
        observations=_strings(payload.get("observations"), "observations"),
        execution_bounds=_mapping_items(payload.get("execution_bounds"), "execution_bounds"),
        cases=_parse_cases(payload.get("cases")),
        provenance=tuple(sorted((provenance_raw or {}).items())),
    )


def load_experiment_spec(path: str | Path) -> ExperimentSpec:
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() != ".json":
        raise ExperimentSpecError("canonical experiment specification must be JSON")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExperimentSpecError(f"invalid JSON: {exc}") from exc
    return validate_payload(payload, source_path=source)


__all__ = [
    "SCHEMA_VERSION", "CaseDeclaration", "ExperimentSpec", "ExperimentSpecError",
    "SpecSemanticError", "UnsupportedCapabilityError", "load_experiment_spec",
    "validate_payload",
]
