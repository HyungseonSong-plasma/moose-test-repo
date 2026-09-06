"""Canonical application boundary for performance measurement and analysis.

This module is intentionally solver-neutral. Concrete MOOSE/PETSc syntax and
raw-format decoding remain behind adapter packages; the CLI routes only here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from qpx_harness.analysis.performance import profile as performance_analysis
from qpx_harness.execution.performance.runner import (
    PerformanceContractError,
    run_measurement as _run_measurement,
    self_test as _measurement_self_test,
)


def run_measurement(
    manifest_path: Path,
    *,
    executable: str | Path | None = None,
    out_dir: Path | None = None,
) -> int:
    return _run_measurement(
        manifest_path,
        executable=executable,
        out_dir=out_dir,
    )


def analyze_profile(
    summary_path: Path,
    petsc_log_path: Path,
    perf_log_path: Path | None = None,
    *,
    metric_prefix: str | None = None,
) -> dict[str, Any]:
    return performance_analysis.analyze(
        summary_path,
        petsc_log_path,
        perf_log_path,
        metric_prefix=metric_prefix,
    )


def self_test() -> int:
    return _measurement_self_test()


__all__ = [
    "PerformanceContractError",
    "analyze_profile",
    "run_measurement",
    "self_test",
]
