"""Application-level parsing of reusable declarative execution options.

This module consumes only the small structural contract required for execution
options. It does not own an experiment schema, protocol registry, scientific
case selection, sequencing, acceptance, or interpretation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol, Any

from physics_harness.execution.runtime import resolve_results_root


class ExecutionOptionSource(Protocol):
    execution: Mapping[str, Any]

    def resolve_path(self, value: str | Path) -> Path: ...


def optional_path(spec: ExecutionOptionSource, key: str) -> Path | None:
    value = spec.execution.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, (str, Path)):
        raise ValueError(f"execution.{key} must be path-like")
    return spec.resolve_path(value)


def experiment_results_root(spec: ExecutionOptionSource, executable: object) -> Path:
    executable_path = executable if isinstance(executable, (str, Path)) else None
    return resolve_results_root(executable_path, optional_path(spec, "results_root"))


def positive_timeout(spec: ExecutionOptionSource, *, default: float, key: str = "timeout_seconds") -> float:
    value = float(spec.execution.get(key, default))
    if value <= 0.0:
        raise ValueError(f"execution.{key} must be positive")
    return value


__all__ = ["ExecutionOptionSource", "experiment_results_root", "optional_path", "positive_timeout"]
