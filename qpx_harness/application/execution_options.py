"""Application-level parsing of reusable declarative execution options.

This module composes ExperimentControl-relative configuration with the mechanical
owners in qpx_harness.execution. It intentionally does not own scientific case
selection, sequencing, acceptance, or interpretation.
"""
from __future__ import annotations

from pathlib import Path

from qpx_harness.execution.runtime import resolve_results_root

from .experiment_spec import ExperimentControl


def optional_path(spec: ExperimentControl, key: str) -> Path | None:
    value = spec.execution.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, (str, Path)):
        raise ValueError(f"execution.{key} must be path-like")
    return spec.resolve_path(value)


def experiment_results_root(spec: ExperimentControl, qpx: object) -> Path:
    executable = qpx if isinstance(qpx, (str, Path)) else None
    return resolve_results_root(executable, optional_path(spec, "results_root"))


def positive_timeout(spec: ExperimentControl, *, default: float, key: str = "timeout_seconds") -> float:
    value = float(spec.execution.get(key, default))
    if value <= 0.0:
        raise ValueError(f"execution.{key} must be positive")
    return value


__all__ = ["experiment_results_root", "optional_path", "positive_timeout"]
