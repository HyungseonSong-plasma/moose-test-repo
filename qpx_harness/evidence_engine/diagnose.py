"""Conservative diagnosis helpers for constant-state Green-Gauss evidence.

The diagnosis layer keeps the existing dictionary API for campaign callers while
also exposing a validated Pydantic report for typed consumers. Failure
localization is deliberately entity-aware: face-level failures retain both the
owning element and face id, while cell-level failures retain the element id.
"""
from __future__ import annotations

from typing import Any, Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field


_DECISION_ORDER = (
    "face value reconstruction",
    "surface vector construction",
    "RZ surface/volume closure",
    "runtime-vs-reconstruction arithmetic path",
    "Green-Gauss constant preservation",
)


class EvidenceTolerances(BaseModel):
    """Validated absolute tolerances for the constant-state evidence cascade."""

    model_config = ConfigDict(frozen=True)

    face_value_abs: float = Field(default=1.0e-14, ge=0.0)
    surface_vector_abs: float = Field(default=1.0e-14, ge=0.0)
    surface_closure_abs: float = Field(default=1.0e-14, ge=0.0)
    gradient_match_abs: float = Field(default=1.0e-12, ge=0.0)
    qpx_gradient_abs: float = Field(default=1.0e-12, ge=0.0)


class FailureLocation(BaseModel):
    """Top-ranked location contributing to the selected diagnosis layer."""

    model_config = ConfigDict(frozen=True)

    entity_kind: Literal["face", "cell"]
    metric: str
    elem_id: int
    face_id: int | None = None
    centroid: tuple[float, float]
    error_value: float = Field(ge=0.0)
    run_id: str | None = None
    case_id: str | None = None


class DiagnosisReport(BaseModel):
    """Validated machine-readable diagnosis for one constant-state evidence set."""

    model_config = ConfigDict(frozen=True)

    status: str
    primary_owner_class: str | None = None
    metrics: dict[str, float]
    failing_locations: list[FailureLocation] = Field(default_factory=list)
    rz_specific_status: str = "REQUIRES_SPATIAL_COMPONENT_AGREEMENT"
    decision_order: list[str] = Field(default_factory=lambda: list(_DECISION_ORDER))


def _require_diagnostic_columns(
    frame: pl.DataFrame,
    *,
    metric: str,
    entity_kind: Literal["face", "cell"],
    x_col: str,
    y_col: str,
) -> None:
    required = {metric, "elem_id", x_col, y_col}
    if entity_kind == "face":
        required.add("face_id")
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(
            f"{entity_kind} diagnosis missing required columns for {metric}: "
            + ", ".join(missing)
        )
    if frame.height == 0:
        raise ValueError(f"{entity_kind} diagnosis received no rows for {metric}")


def _max_and_failures(
    frame: pl.DataFrame,
    metric: str,
    threshold: float,
    *,
    entity_kind: Literal["face", "cell"],
    x_col: str,
    y_col: str,
    top_k: int,
) -> tuple[float, list[FailureLocation]]:
    """Return the absolute maximum and top-K threshold violations.

    Missing/non-finite evidence is a contract error, never numerical zero. This
    prevents an incomplete telemetry bundle from being misclassified as a PASS.
    """
    if top_k <= 0:
        raise ValueError("top_k_failures must be positive")
    _require_diagnostic_columns(
        frame,
        metric=metric,
        entity_kind=entity_kind,
        x_col=x_col,
        y_col=y_col,
    )

    invalid_count = frame.select(
        pl.col(metric).is_finite().fill_null(False).not_().sum()
    ).item()
    if int(invalid_count or 0) != 0:
        raise ValueError(f"{entity_kind} diagnosis metric {metric} contains non-finite values")

    max_value = frame.select(pl.col(metric).abs().max()).item()
    maximum = float(max_value if max_value is not None else 0.0)
    if maximum <= threshold:
        return maximum, []

    failed = (
        frame.with_columns(pl.col(metric).abs().alias("__abs_error"))
        .filter(pl.col("__abs_error") > threshold)
        .sort("__abs_error", descending=True)
        .head(top_k)
    )

    locations: list[FailureLocation] = []
    for row in failed.iter_rows(named=True):
        locations.append(
            FailureLocation(
                entity_kind=entity_kind,
                metric=metric,
                elem_id=int(row["elem_id"]),
                face_id=(int(row["face_id"]) if entity_kind == "face" else None),
                centroid=(float(row[x_col]), float(row[y_col])),
                error_value=float(row["__abs_error"]),
                run_id=(str(row["run_id"]) if row.get("run_id") is not None else None),
                case_id=(str(row["case_id"]) if row.get("case_id") is not None else None),
            )
        )
    return maximum, locations


def _max_metric(frame: pl.DataFrame, metric: str) -> float:
    if metric not in frame.columns:
        raise ValueError(f"diagnosis missing required metric column: {metric}")
    if frame.height == 0:
        raise ValueError(f"diagnosis received no rows for metric {metric}")
    invalid_count = frame.select(
        pl.col(metric).is_finite().fill_null(False).not_().sum()
    ).item()
    if int(invalid_count or 0) != 0:
        raise ValueError(f"diagnosis metric {metric} contains non-finite values")
    value = frame.select(pl.col(metric).abs().max()).item()
    return float(value if value is not None else 0.0)


def summarize_constant_state_report(
    face: pl.DataFrame,
    cell: pl.DataFrame,
    *,
    tolerances: EvidenceTolerances | None = None,
    top_k_failures: int = 5,
) -> DiagnosisReport:
    """Return a typed report for the first failing constant-state evidence layer.

    The function deliberately stops short of declaring an RZ-specific atomic
    mechanism from magnitude agreement alone. That attribution requires spatial
    and component agreement with the MOOSE runtime path.
    """
    if top_k_failures <= 0:
        raise ValueError("top_k_failures must be positive")
    tol = tolerances or EvidenceTolerances()

    max_n_face_delta, face_value_failures = _max_and_failures(
        face,
        "n_face_delta",
        tol.face_value_abs,
        entity_kind="face",
        x_col="face_x",
        y_col="face_y",
        top_k=top_k_failures,
    )
    max_surface_delta, surface_failures = _max_and_failures(
        face,
        "surface_delta_norm",
        tol.surface_vector_abs,
        entity_kind="face",
        x_col="face_x",
        y_col="face_y",
        top_k=top_k_failures,
    )
    max_closure_norm, closure_failures = _max_and_failures(
        cell,
        "surface_closure_norm",
        tol.surface_closure_abs,
        entity_kind="cell",
        x_col="cell_x",
        y_col="cell_y",
        top_k=top_k_failures,
    )
    max_grad_delta, gradient_delta_failures = _max_and_failures(
        cell,
        "gradient_delta_norm",
        tol.gradient_match_abs,
        entity_kind="cell",
        x_col="cell_x",
        y_col="cell_y",
        top_k=top_k_failures,
    )
    max_qpx_grad, qpx_gradient_failures = _max_and_failures(
        cell,
        "qpx_grad_norm",
        tol.qpx_gradient_abs,
        entity_kind="cell",
        x_col="cell_x",
        y_col="cell_y",
        top_k=top_k_failures,
    )

    metrics = {
        "max_abs_n_face_delta": max_n_face_delta,
        "max_surface_delta_norm": max_surface_delta,
        "max_surface_closure_norm": max_closure_norm,
        "max_gradient_delta_norm": max_grad_delta,
        "max_qpx_grad_norm": max_qpx_grad,
        "max_reconstructed_grad_norm": _max_metric(cell, "reconstructed_grad_norm"),
    }

    if max_n_face_delta > tol.face_value_abs:
        owner = "FACE_VALUE_RECONSTRUCTION"
        status = "ISOLATED_OWNER_CLASS"
        failures = face_value_failures
    elif max_surface_delta > tol.surface_vector_abs:
        owner = "SURFACE_VECTOR_CONSTRUCTION"
        status = "ISOLATED_OWNER_CLASS"
        failures = surface_failures
    elif max_closure_norm > tol.surface_closure_abs:
        owner = "RZ_SURFACE_GEOMETRY_CLOSURE"
        status = "FAVORED"
        failures = closure_failures
    elif max_grad_delta > tol.gradient_match_abs:
        owner = "MISSING_MOOSE_ARITHMETIC_PATH"
        status = "UNRESOLVED"
        failures = gradient_delta_failures
    elif max_qpx_grad > tol.qpx_gradient_abs:
        owner = "FV_GREEN_GAUSS_CELL_GRADIENT_CONSTANT_PRESERVATION"
        status = "ISOLATED_OWNER_CLASS"
        failures = qpx_gradient_failures
    else:
        owner = None
        status = "CONSTANT_STATE_PASS"
        failures = []

    return DiagnosisReport(
        status=status,
        primary_owner_class=owner,
        metrics=metrics,
        failing_locations=failures,
    )


def summarize_constant_state(
    face: pl.DataFrame,
    cell: pl.DataFrame,
    *,
    tolerances: EvidenceTolerances | None = None,
    top_k_failures: int = 5,
) -> dict[str, Any]:
    """Compatibility wrapper returning the validated report as a dictionary."""
    return summarize_constant_state_report(
        face,
        cell,
        tolerances=tolerances,
        top_k_failures=top_k_failures,
    ).model_dump(mode="python")
