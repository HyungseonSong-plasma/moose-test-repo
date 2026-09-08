"""Application composition for gradient-reconstruction evidence.

The application layer selects a reconstruction method explicitly, normalizes
its external telemetry contract, and delegates quantitative formulas to the
method implementation in :mod:`qpx_harness.analysis`.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from qpx_harness.evidence.schema import GREEN_GAUSS_FACE_CONTRACT, DynamicSchemaContract
from qpx_harness.evidence.transform import normalize_face_evidence

FrameLike = pl.DataFrame | pl.LazyFrame
SUPPORTED_RECONSTRUCTION_METHODS = frozenset({"green_gauss"})


def _method_contract(method: str) -> DynamicSchemaContract:
    if method == "green_gauss":
        return GREEN_GAUSS_FACE_CONTRACT
    raise ValueError(
        f"unsupported gradient-reconstruction method {method!r}; "
        f"expected one of {sorted(SUPPORTED_RECONSTRUCTION_METHODS)}"
    )


def _derive(method: str, normalized: pl.DataFrame, *, radial_component: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    if method == "green_gauss":
        from qpx_harness.analysis.gradient_reconstruction.green_gauss import derive_cell_quantities, derive_face_quantities

        face = derive_face_quantities(normalized)
        cell = derive_cell_quantities(normalized, radial_component=radial_component)
        return face, cell
    raise AssertionError(f"validated method lost dispatch implementation: {method}")


def analyze_gradient_reconstruction(
    frame: FrameLike,
    *,
    method: str,
    radial_component: int = 0,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Normalize method telemetry and derive canonical face/cell facts."""
    contract = _method_contract(method)
    normalized = normalize_face_evidence(frame, schema_contract=contract)
    return _derive(method, normalized, radial_component=radial_component)


def prepare_reconstruction_face_evidence(
    frame: FrameLike,
    *,
    method: str,
) -> pl.DataFrame:
    face, _ = analyze_gradient_reconstruction(frame, method=method)
    return face


def build_reconstruction_cell_evidence(
    frame: FrameLike,
    *,
    method: str,
    radial_component: int = 0,
) -> pl.DataFrame:
    _, cell = analyze_gradient_reconstruction(
        frame, method=method, radial_component=radial_component
    )
    return cell


def write_reconstruction_evidence_bundle(
    frame: FrameLike,
    root: Path,
    *,
    method: str,
    radial_component: int = 0,
) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    face, cell = analyze_gradient_reconstruction(
        frame, method=method, radial_component=radial_component
    )
    face_path = root / "face_evidence.parquet"
    cell_path = root / "cell_evidence.parquet"
    face.write_parquet(face_path)
    cell.write_parquet(cell_path)
    return {"face_evidence": str(face_path), "cell_evidence": str(cell_path)}


__all__ = [
    "SUPPORTED_RECONSTRUCTION_METHODS",
    "analyze_gradient_reconstruction",
    "build_reconstruction_cell_evidence",
    "prepare_reconstruction_face_evidence",
    "write_reconstruction_evidence_bundle",
]
