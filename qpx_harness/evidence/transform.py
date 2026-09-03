"""Source-faithful normalization and persistence for face evidence.

Quantitative Green-Gauss reconstruction belongs to ``qpx_harness.analysis``.
Compatibility wrappers remain here so existing callers keep their result shape
while dependency ownership migrates to the canonical Analysis layer.
"""
from __future__ import annotations

from pathlib import Path

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


def prepare_face_evidence(
    frame: FrameLike,
    *,
    schema_contract: DynamicSchemaContract = DEFAULT_FACE_CONTRACT,
) -> pl.DataFrame:
    """Compatibility facade returning the historical derived face table."""
    from qpx_harness.analysis.green_gauss import derive_face_quantities

    return derive_face_quantities(normalize_face_evidence(frame, schema_contract=schema_contract))


def build_cell_evidence(
    face_frame: FrameLike,
    *,
    radial_component: int = 0,
    schema_contract: DynamicSchemaContract = DEFAULT_FACE_CONTRACT,
) -> pl.DataFrame:
    """Compatibility facade for the Analysis-owned cell reconstruction."""
    from qpx_harness.analysis.green_gauss import derive_cell_quantities

    normalized = normalize_face_evidence(face_frame, schema_contract=schema_contract)
    return derive_cell_quantities(normalized, radial_component=radial_component)


def write_evidence_bundle(
    face_frame: FrameLike,
    root: Path,
    *,
    radial_component: int = 0,
    schema_contract: DynamicSchemaContract = DEFAULT_FACE_CONTRACT,
) -> dict[str, str]:
    """Persist historical derived face/cell tables through canonical owners."""
    from qpx_harness.analysis.green_gauss import derive_cell_quantities, derive_face_quantities

    root.mkdir(parents=True, exist_ok=True)
    normalized = normalize_face_evidence(face_frame, schema_contract=schema_contract)
    face = derive_face_quantities(normalized)
    cell = derive_cell_quantities(normalized, radial_component=radial_component)
    face_path = root / "face_evidence.parquet"
    cell_path = root / "cell_evidence.parquet"
    face.write_parquet(face_path)
    cell.write_parquet(cell_path)
    return {"face_evidence": str(face_path), "cell_evidence": str(cell_path)}


__all__ = ["build_cell_evidence", "normalize_face_evidence", "prepare_face_evidence", "write_evidence_bundle"]
