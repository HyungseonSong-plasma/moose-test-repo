"""Side-effect-free JSON loading for ExperimentSpec v1."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import ExperimentSpecError, SpecProblem
from .models import ExperimentSpec, model_validate


def _validation_problems(exc: ValidationError) -> tuple[SpecProblem, ...]:
    problems: list[SpecProblem] = []
    for item in exc.errors():
        location = tuple(item.get("loc", ()))
        context = tuple(
            sorted((str(key), str(value)) for key, value in (item.get("ctx") or {}).items())
        )
        problems.append(
            SpecProblem(
                code="SPEC_VALIDATION_ERROR",
                message=str(item.get("msg", "invalid ExperimentSpec")),
                location=location,
                context=context,
            )
        )
    return tuple(problems)


def load_payload(payload: Any) -> ExperimentSpec:
    try:
        return model_validate(payload)
    except ValidationError as exc:
        raise ExperimentSpecError(_validation_problems(exc)) from exc


def load_json_text(text: str) -> ExperimentSpec:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExperimentSpecError(
            (
                SpecProblem(
                    code="SPEC_JSON_DECODE_ERROR",
                    message=exc.msg,
                    location=(exc.lineno, exc.colno),
                ),
            )
        ) from exc
    return load_payload(payload)


def load_json_file(path: Path) -> ExperimentSpec:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ExperimentSpecError(
            (
                SpecProblem(
                    code="SPEC_IO_ERROR",
                    message=str(exc),
                    location=(str(path),),
                ),
            )
        ) from exc
    return load_json_text(text)
