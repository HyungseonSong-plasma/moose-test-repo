"""Compatibility facade for generic QPX process execution."""

from .execution.runtime import (
    RunResult,
    TelemetryCallback,
    TelemetrySample,
    resolve_executable,
    run_command,
    run_qpx,
    validate_executable,
)

__all__ = [
    "RunResult",
    "TelemetryCallback",
    "TelemetrySample",
    "resolve_executable",
    "run_command",
    "run_qpx",
    "validate_executable",
]
