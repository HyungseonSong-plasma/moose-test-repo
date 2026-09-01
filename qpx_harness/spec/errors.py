"""Structured ExperimentSpec validation/compilation errors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SpecProblem:
    code: str
    message: str
    location: tuple[str | int, ...] = ()
    context: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "location": list(self.location),
            "context": dict(self.context),
        }


class ExperimentSpecError(ValueError):
    """Base structured failure for declarative experiment specifications."""

    def __init__(self, problems: tuple[SpecProblem, ...]):
        if not problems:
            raise ValueError("ExperimentSpecError requires at least one problem")
        self.problems = problems
        super().__init__("; ".join(problem.message for problem in problems))

    @property
    def code(self) -> str:
        return self.problems[0].code

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": "ExperimentSpecError",
            "problems": [problem.as_dict() for problem in self.problems],
        }


class ExperimentSpecDependencyError(RuntimeError):
    """Raised when the strict schema dependency is unavailable."""
