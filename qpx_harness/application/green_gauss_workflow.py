"""Application composition for normalized Green-Gauss analysis artifacts.

Evidence owns source-faithful normalization. Analysis owns quantitative
Green-Gauss derivation. This downstream Application module composes those
owners for callers that need the historical face/cell artifact pair.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from qpx_harness.analysis.green_gauss import derive_cell_quantities, derive_face_quantities
from qpx_harness.evidence.schema import DEFAULT_FACE_CONTRACT, DynamicSchemaContract
from qpx_harness.evidence.transform import normalize_face_evidence

FrameLike = pl.DataFrame | pl.LazyFrame


def prepare_face_evidence(
    frame: FrameLike,
    *,
    schema_contract: DynamicSchemaContract = DEFAULT_FACE_CONTRACT,
) -> pl.DataFrame:
    normalized = normalize_face_evidence(frame, schema_contract=schema_contract)
    return derive_face_quantities(normalized)


def build_cell_evidence(
    face_frame: FrameLike,
    *,
    radial_component: int = 0,
    schema_contract: DynamicSchemaContract = DEFAULT_FACE_CONTRACT,
) -> pl.DataFrame:
    normalized = normalize_face_evidence(face_frame, schema_contract=schema_contract)
    return derive_cell_quantities(normalized, radial_component=radial_component)


def write_evidence_bundle(
    face_frame: FrameLike,
    root: Path,
    *,
    radial_component: int = 0,
    schema_contract: DynamicSchemaContract = DEFAULT_FACE_CONTRACT,
) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    normalized = normalize_face_evidence(face_frame, schema_contract=schema_contract)
    face = derive_face_quantities(normalized)
    cell = derive_cell_quantities(normalized, radial_component=radial_component)
    face_path = root / "face_evidence.parquet"
    cell_path = root / "cell_evidence.parquet"
    face.write_parquet(face_path)
    cell.write_parquet(cell_path)
    return {"face_evidence": str(face_path), "cell_evidence": str(cell_path)}


__all__ = ["build_cell_evidence", "prepare_face_evidence", "write_evidence_bundle"]
