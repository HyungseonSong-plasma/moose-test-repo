"""Deterministic quantitative aggregation for diagnostic reasoning inputs."""
from __future__ import annotations

from collections.abc import Mapping

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DiagnosticMetricSpec(BaseModel):
    """Describe one scalar diagnostic metric derived from a named evidence frame."""

    model_config = ConfigDict(frozen=True)

    metric_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    column: str = Field(min_length=1)
    report_key: str = Field(min_length=1)
    entity_kind: str | None = None
    x_col: str | None = None
    y_col: str | None = None

    @model_validator(mode="after")
    def _validate_location_columns(self) -> "DiagnosticMetricSpec":
        if self.entity_kind is None:
            if self.x_col is not None or self.y_col is not None:
                raise ValueError("non-spatial metrics may not declare centroid columns")
            return self
        if self.entity_kind not in {"face", "cell"}:
            raise ValueError("entity_kind must be face, cell, or omitted")
        if self.x_col is None or self.y_col is None:
            raise ValueError("spatial metrics require both x_col and y_col")
        return self


def frame_for_metric(
    frames: Mapping[str, pl.DataFrame], metric: DiagnosticMetricSpec
) -> pl.DataFrame:
    frame = frames.get(metric.source)
    if frame is None:
        raise ValueError(
            f"diagnostic metric {metric.metric_id!r} requires missing source frame "
            f"{metric.source!r}"
        )
    if frame.height == 0:
        raise ValueError(
            f"diagnostic metric {metric.metric_id!r} received no rows from "
            f"source {metric.source!r}"
        )
    if metric.column not in frame.columns:
        raise ValueError(
            f"diagnostic metric {metric.metric_id!r} missing required column: {metric.column}"
        )
    return frame


def metric_max_abs(frame: pl.DataFrame, metric: DiagnosticMetricSpec) -> float:
    invalid_count = frame.select(
        pl.col(metric.column).is_finite().fill_null(False).not_().sum()
    ).item()
    if int(invalid_count or 0) != 0:
        raise ValueError(
            f"diagnostic metric {metric.metric_id!r} column {metric.column!r} "
            "contains non-finite values"
        )
    value = frame.select(pl.col(metric.column).abs().max()).item()
    return float(value if value is not None else 0.0)


def aggregate_metric_values(
    frames: Mapping[str, pl.DataFrame],
    metrics: Mapping[str, DiagnosticMetricSpec],
) -> tuple[dict[str, float], dict[str, float], dict[str, pl.DataFrame]]:
    """Return report-key values, rule-input values, and resolved source frames."""
    report_values: dict[str, float] = {}
    metric_values: dict[str, float] = {}
    frames_by_metric: dict[str, pl.DataFrame] = {}
    report_keys: set[str] = set()
    for metric_id, metric in metrics.items():
        if metric_id != metric.metric_id:
            raise ValueError(
                f"metric registry key {metric_id!r} must equal metric_id {metric.metric_id!r}"
            )
        if metric.report_key in report_keys:
            raise ValueError(f"duplicate diagnostic report key: {metric.report_key!r}")
        report_keys.add(metric.report_key)
        frame = frame_for_metric(frames, metric)
        frames_by_metric[metric_id] = frame
        value = metric_max_abs(frame, metric)
        metric_values[metric_id] = value
        report_values[metric.report_key] = value
    return report_values, metric_values, frames_by_metric


def failure_location_rows(
    frame: pl.DataFrame,
    metric: DiagnosticMetricSpec,
    threshold: float,
    *,
    inclusive: bool,
    top_k: int,
) -> list[dict[str, object]]:
    """Extract deterministic spatial failure rows without assigning semantics."""
    if metric.entity_kind is None:
        return []
    if top_k <= 0:
        raise ValueError("top_k_failures must be positive")
    required = {"elem_id", metric.x_col, metric.y_col}
    if metric.entity_kind == "face":
        required.add("face_id")
    missing = sorted(str(name) for name in required if name not in frame.columns)
    if missing:
        raise ValueError(
            f"{metric.entity_kind} diagnostic missing location columns for "
            f"{metric.metric_id}: {', '.join(missing)}"
        )

    absolute_error = pl.col(metric.column).abs()
    predicate = absolute_error >= threshold if inclusive else absolute_error > threshold
    failed = (
        frame.with_columns(absolute_error.alias("__abs_error"))
        .filter(predicate)
        .sort("__abs_error", descending=True)
        .head(top_k)
    )
    rows: list[dict[str, object]] = []
    for row in failed.iter_rows(named=True):
        rows.append(
            {
                "entity_kind": metric.entity_kind,
                "metric": metric.column,
                "elem_id": int(row["elem_id"]),
                "face_id": int(row["face_id"]) if metric.entity_kind == "face" else None,
                "centroid": (float(row[metric.x_col]), float(row[metric.y_col])),
                "error_value": float(row["__abs_error"]),
                "run_id": str(row["run_id"]) if row.get("run_id") is not None else None,
                "case_id": str(row["case_id"]) if row.get("case_id") is not None else None,
            }
        )
    return rows


__all__ = [
    "DiagnosticMetricSpec",
    "aggregate_metric_values",
    "failure_location_rows",
    "frame_for_metric",
    "metric_max_abs",
]
