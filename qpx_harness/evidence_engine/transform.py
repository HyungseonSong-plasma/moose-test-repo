"""Polars transformations for MOOSE face telemetry and cell reconstruction."""
from __future__ import annotations

from pathlib import Path

import polars as pl

from .schema import CELL_KEY_COLUMNS, FACE_REQUIRED_COLUMNS, require_columns

FrameLike = pl.DataFrame | pl.LazyFrame


def _lazy(frame: FrameLike) -> pl.LazyFrame:
    return frame.lazy() if isinstance(frame, pl.DataFrame) else frame


def _columns(frame: FrameLike) -> list[str]:
    if isinstance(frame, pl.DataFrame):
        return frame.columns
    return frame.collect_schema().names()


def prepare_face_evidence(frame: FrameLike) -> pl.DataFrame:
    """Add independently reconstructed surface/weighted-face evidence.

    ``moose_surface_*`` columns are never overwritten: they remain runtime truth.
    ``reconstructed_surface_*`` uses normal * face_area * coord_factor so the
    surface-vector construction path can be compared explicitly.
    """
    require_columns(_columns(frame), FACE_REQUIRED_COLUMNS, context="face telemetry")
    return (
        _lazy(frame)
        .with_columns(
            (pl.col("normal_x") * pl.col("face_area") * pl.col("coord_factor")).alias(
                "reconstructed_surface_x"
            ),
            (pl.col("normal_y") * pl.col("face_area") * pl.col("coord_factor")).alias(
                "reconstructed_surface_y"
            ),
            (pl.col("n_face") - pl.col("n_cell")).alias("n_face_delta"),
        )
        .with_columns(
            (pl.col("moose_surface_x") - pl.col("reconstructed_surface_x")).alias(
                "surface_delta_x"
            ),
            (pl.col("moose_surface_y") - pl.col("reconstructed_surface_y")).alias(
                "surface_delta_y"
            ),
            (pl.col("n_face") * pl.col("moose_surface_x")).alias("weighted_moose_x"),
            (pl.col("n_face") * pl.col("moose_surface_y")).alias("weighted_moose_y"),
            (pl.col("n_face") * pl.col("reconstructed_surface_x")).alias(
                "weighted_reconstructed_x"
            ),
            (pl.col("n_face") * pl.col("reconstructed_surface_y")).alias(
                "weighted_reconstructed_y"
            ),
        )
        .with_columns(
            ((pl.col("surface_delta_x") ** 2 + pl.col("surface_delta_y") ** 2).sqrt()).alias(
                "surface_delta_norm"
            )
        )
        .collect()
    )


def build_cell_evidence(face_frame: FrameLike, *, radial_component: int = 0) -> pl.DataFrame:
    """Aggregate face evidence and reconstruct the Green-Gauss cell gradient.

    ``radial_component=0`` corresponds to the accepted R3 convention where the
    symmetry axis is Y and the radial coordinate is X. Component 1 supports the
    opposite 2-D orientation for reuse in other cases.
    """
    if radial_component not in (0, 1):
        raise ValueError("radial_component must be 0 (X) or 1 (Y)")

    face = prepare_face_evidence(face_frame)
    require_columns(face.columns, CELL_KEY_COLUMNS, context="prepared face evidence")

    return (
        face.lazy()
        .group_by(list(CELL_KEY_COLUMNS))
        .agg(
            pl.first("cell_x").alias("cell_x"),
            pl.first("cell_y").alias("cell_y"),
            pl.first("cell_volume").alias("cell_volume"),
            pl.first("radial_coordinate").alias("radial_coordinate"),
            pl.first("n_cell").alias("n_cell"),
            pl.first("qpx_grad_x").alias("qpx_grad_x"),
            pl.first("qpx_grad_y").alias("qpx_grad_y"),
            pl.len().alias("face_count"),
            pl.col("moose_surface_x").sum().alias("sum_moose_surface_x"),
            pl.col("moose_surface_y").sum().alias("sum_moose_surface_y"),
            pl.col("reconstructed_surface_x").sum().alias("sum_reconstructed_surface_x"),
            pl.col("reconstructed_surface_y").sum().alias("sum_reconstructed_surface_y"),
            pl.col("weighted_moose_x").sum().alias("sum_weighted_moose_x"),
            pl.col("weighted_moose_y").sum().alias("sum_weighted_moose_y"),
            pl.col("weighted_reconstructed_x").sum().alias("sum_weighted_reconstructed_x"),
            pl.col("weighted_reconstructed_y").sum().alias("sum_weighted_reconstructed_y"),
            pl.col("surface_delta_norm").max().alias("max_surface_delta_norm"),
            pl.col("n_face_delta").abs().max().alias("max_abs_n_face_delta"),
        )
        .with_columns(
            (pl.col("sum_weighted_moose_x") / pl.col("cell_volume")).alias("pre_rz_grad_x"),
            (pl.col("sum_weighted_moose_y") / pl.col("cell_volume")).alias("pre_rz_grad_y"),
            (pl.col("sum_moose_surface_x") / pl.col("cell_volume")).alias(
                "surface_balance_x"
            ),
            (pl.col("sum_moose_surface_y") / pl.col("cell_volume")).alias(
                "surface_balance_y"
            ),
        )
        .with_columns(
            (
                pl.when(pl.lit(radial_component) == 0)
                .then(pl.col("n_cell") / pl.col("radial_coordinate"))
                .otherwise(0.0)
            ).alias("rz_correction_x"),
            (
                pl.when(pl.lit(radial_component) == 1)
                .then(pl.col("n_cell") / pl.col("radial_coordinate"))
                .otherwise(0.0)
            ).alias("rz_correction_y"),
            (
                pl.when(pl.lit(radial_component) == 0)
                .then(1.0 / pl.col("radial_coordinate"))
                .otherwise(0.0)
            ).alias("unit_rz_correction_x"),
            (
                pl.when(pl.lit(radial_component) == 1)
                .then(1.0 / pl.col("radial_coordinate"))
                .otherwise(0.0)
            ).alias("unit_rz_correction_y"),
        )
        .with_columns(
            (pl.col("pre_rz_grad_x") - pl.col("rz_correction_x")).alias(
                "reconstructed_grad_x"
            ),
            (pl.col("pre_rz_grad_y") - pl.col("rz_correction_y")).alias(
                "reconstructed_grad_y"
            ),
            (pl.col("surface_balance_x") - pl.col("unit_rz_correction_x")).alias(
                "surface_closure_x"
            ),
            (pl.col("surface_balance_y") - pl.col("unit_rz_correction_y")).alias(
                "surface_closure_y"
            ),
        )
        .with_columns(
            (pl.col("qpx_grad_x") - pl.col("reconstructed_grad_x")).alias("gradient_delta_x"),
            (pl.col("qpx_grad_y") - pl.col("reconstructed_grad_y")).alias("gradient_delta_y"),
            ((pl.col("reconstructed_grad_x") ** 2 + pl.col("reconstructed_grad_y") ** 2).sqrt()).alias(
                "reconstructed_grad_norm"
            ),
            ((pl.col("qpx_grad_x") ** 2 + pl.col("qpx_grad_y") ** 2).sqrt()).alias(
                "qpx_grad_norm"
            ),
            ((pl.col("surface_closure_x") ** 2 + pl.col("surface_closure_y") ** 2).sqrt()).alias(
                "surface_closure_norm"
            ),
        )
        .with_columns(
            ((pl.col("gradient_delta_x") ** 2 + pl.col("gradient_delta_y") ** 2).sqrt()).alias(
                "gradient_delta_norm"
            )
        )
        .collect()
    )


def write_evidence_bundle(
    face_frame: FrameLike,
    root: Path,
    *,
    radial_component: int = 0,
) -> dict[str, str]:
    """Write canonical face/cell Parquet evidence and return artifact paths."""
    root.mkdir(parents=True, exist_ok=True)
    face = prepare_face_evidence(face_frame)
    cell = build_cell_evidence(face, radial_component=radial_component)
    face_path = root / "face_evidence.parquet"
    cell_path = root / "cell_evidence.parquet"
    face.write_parquet(face_path)
    cell.write_parquet(cell_path)
    return {"face_evidence": str(face_path), "cell_evidence": str(cell_path)}
