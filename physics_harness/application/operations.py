"""Reusable cross-subsystem application operations.

Application services compose subsystem APIs. They do not own scientific
formulas, diagnosis thresholds, or low-level process/workspace mechanics.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from physics_harness.application.gradient_reconstruction import analyze_gradient_reconstruction as _analyze_gradient_reconstruction


def analyze_gradient_reconstruction(
    face_frame: Any,
    *,
    method: str,
    radial_component: int = 0,
) -> tuple[Any, Any]:
    """Analyze one explicitly selected gradient-reconstruction method."""
    return _analyze_gradient_reconstruction(
        face_frame, method=method, radial_component=radial_component
    )


def diagnose_constant_reconstruction(
    face_frame: Any,
    *,
    method: str,
    radial_component: int = 0,
    tolerances: Any | None = None,
) -> dict[str, Any]:
    """Compose Evidence -> Analysis -> Reasoning for a constant-state check."""
    from physics_harness.reasoning.gradient_reconstruction import summarize_constant_state

    face, cell = analyze_gradient_reconstruction(
        face_frame, method=method, radial_component=radial_component
    )
    kwargs = {} if tolerances is None else {"tolerances": tolerances}
    return summarize_constant_state(face, cell, method=method, **kwargs)


def normalize_temporal_run_csv(
    source: str | Path,
    output: str | Path,
    *,
    time_column: str,
    initial_row_policy: str,
    initial_time: float,
    time_tol: float,
    require_physical_rows: bool,
) -> dict[str, Any]:
    from physics_harness.analysis.temporal import normalize_temporal_csv

    return normalize_temporal_csv(
        Path(source),
        Path(output),
        time_column=time_column,
        initial_row_policy=initial_row_policy,
        initial_time=initial_time,
        time_tol=time_tol,
        require_physical_rows=require_physical_rows,
    )


__all__ = [
    "analyze_gradient_reconstruction",
    "diagnose_constant_reconstruction",
    "normalize_temporal_run_csv",
]
