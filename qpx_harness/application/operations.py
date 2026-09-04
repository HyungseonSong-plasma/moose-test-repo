"""Reusable cross-subsystem application operations.

Application services compose subsystem APIs. They do not own scientific
formulas, diagnosis thresholds, or low-level process/workspace mechanics.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from qpx_harness.analysis.green_gauss import derive_cell_quantities, derive_face_quantities
from qpx_harness.evidence import normalize_face_evidence


def analyze_green_gauss(face_frame: Any, *, radial_component: int = 0) -> tuple[Any, Any]:
    """Normalize source face evidence and derive face/cell quantitative facts."""
    normalized = normalize_face_evidence(face_frame)
    return derive_face_quantities(normalized), derive_cell_quantities(normalized, radial_component=radial_component)


def diagnose_constant_green_gauss(
    face_frame: Any,
    *,
    radial_component: int = 0,
    tolerances: Any | None = None,
) -> dict[str, Any]:
    """Compose Evidence -> Analysis -> Reasoning/Validation for constant-state diagnostics."""
    from qpx_harness.validation.green_gauss import summarize_constant_state

    face, cell = analyze_green_gauss(face_frame, radial_component=radial_component)
    kwargs = {} if tolerances is None else {"tolerances": tolerances}
    return summarize_constant_state(face, cell, **kwargs)


def preflight_input(path: str | Path) -> None:
    from qpx_harness.moose.preflight import validate_input_preflight

    validate_input_preflight(Path(path).expanduser().resolve())


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
    from qpx_harness.analysis.temporal import normalize_temporal_csv

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
    "analyze_green_gauss",
    "diagnose_constant_green_gauss",
    "normalize_temporal_run_csv",
    "preflight_input",
]
