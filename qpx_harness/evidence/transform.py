"""Source-faithful normalization for face evidence.

Quantitative Green-Gauss reconstruction belongs to ``qpx_harness.analysis``.
Cross-layer composition belongs downstream in ``qpx_harness.application``.
"""
from __future__ import annotations

import polars as pl

from .schema import DEFAULT_FACE_CONTRACT, FACE_REQUIRED_COLUMNS, DynamicSchemaContract, normalize_and_project, require_columns

FrameLike = pl.DataFrame | pl.LazyFrame


def _columns(frame: FrameLike) -> list[str]:
    if isinstance(frame, pl.DataFrame):
        return frame.columns
    return frame.collect_schema().names()


def normalize_face_evidence(
    frame: FrameLike,
    *,
    schema_contract: DynamicSchemaContract = DEFAULT_FACE_CONTRACT,
) -> pl.DataFrame:
    """Return canonical source-faithful face telemetry without derived science."""
    normalized = normalize_and_project(frame, schema_contract, context="face telemetry")
    require_columns(_columns(normalized), FACE_REQUIRED_COLUMNS, context="normalized face telemetry")
    return normalized.collect() if isinstance(normalized, pl.LazyFrame) else normalized


__all__ = ["normalize_face_evidence"]
