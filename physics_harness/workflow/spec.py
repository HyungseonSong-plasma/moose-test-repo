"""Validated, immutable *intent* for per-case CI; does not authorize execution."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Case:
    id: str


@dataclass(frozen=True)
class WorkflowSpec:
    schema_version: int
    name: str
    profile: str
    source_sha: str
    oci_ref: str
    cases: tuple[Case, ...]
    max_parallel: int
    timeout_minutes: int
    artifact_prefix: str
    build_script: str | None = None
    case_script: str | None = None
    end_time_s: float | None = None
    intervals: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowSpec":
        from physics_harness.workflow.validator import WorkflowValidationError, validate_spec
        if not isinstance(data, dict):
            raise WorkflowValidationError("SPEC_NOT_OBJECT")
        allowed = {field for field in cls.__dataclass_fields__}
        if set(data) - allowed:
            raise WorkflowValidationError("SPEC_UNKNOWN_KEYS")
        try:
            cases = data["cases"]
            if not isinstance(cases, list) or any(not isinstance(c, dict) or set(c) != {"id"} for c in cases):
                raise WorkflowValidationError("INVALID_CASES")
            values = dict(data)
            values["cases"] = tuple(Case(**c) for c in cases)
            result = cls(**values)
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkflowValidationError("INVALID_SPEC_FIELDS") from exc
        validate_spec(result)
        return result


def load_spec(path: Path) -> WorkflowSpec:
    from physics_harness.workflow.validator import WorkflowValidationError
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowValidationError("SPEC_UNREADABLE") from exc
    return WorkflowSpec.from_dict(data)
