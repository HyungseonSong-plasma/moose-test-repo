"""Quantitative Green-Gauss derivations from normalized face evidence.

Evidence owns source-faithful telemetry normalization. This module owns
quantities derived from those facts: reconstructed surfaces, weighted sums,
cell aggregation, RZ corrections, gradients, closure measures, and deltas.
"""
from __future__ import annotations

import polars as pl

from qpx_harness.evidence.schema import CELL_KEY_COLUMNS, require_columns

FrameLike = pl.DataFrame | pl.LazyFrame


def _lazy(frame: FrameLike) -> pl.LazyFrame:
    return frame.lazy() if isinstance(frame, pl.DataFrame) else frame


def derive_face_quantities(face_frame: FrameLike) -> pl.DataFrame:
    """Derive reconstructed/weighted face quantities from normalized evidence."""
    return (
        _lazy(face_frame)
        .with_columns(
            (pl.col("normal_x") * pl.col("face_area") * pl.col("coord_factor")).alias("reconstructed_surface_x"),
            (pl.col("normal_y") * pl.col("face_area") * pl.col("coord_factor")).alias("reconstructed_surface_y"),
            (pl.col("field_face") - pl.col("field_cell")).alias("field_face_delta"),
        )
        .with_columns(
            (pl.col("runtime_surface_x") - pl.col("reconstructed_surface_x")).alias("surface_delta_x"),
            (pl.col("runtime_surface_y") - pl.col("reconstructed_surface_y")).alias("surface_delta_y"),
            (pl.col("field_face") * pl.col("runtime_surface_x")).alias("weighted_runtime_x"),
            (pl.col("field_face") * pl.col("runtime_surface_y")).alias("weighted_runtime_y"),
            (pl.col("field_face") * pl.col("reconstructed_surface_x")).alias("weighted_reconstructed_x"),
            (pl.col("field_face") * pl.col("reconstructed_surface_y")).alias("weighted_reconstructed_y"),
        )
        .with_columns(
            ((pl.col("surface_delta_x") ** 2 + pl.col("surface_delta_y") ** 2).sqrt()).alias("surface_delta_norm")
        )
        .collect()
    )


def derive_cell_quantities(face_frame: FrameLike, *, radial_component: int = 0) -> pl.DataFrame:
    """Aggregate face quantities and derive a Green-Gauss cell reconstruction."""
    if radial_component not in (0, 1):
        raise ValueError("radial_component must be 0 (X) or 1 (Y)")
    face = derive_face_quantities(face_frame)
    require_columns(face.columns, CELL_KEY_COLUMNS, context="derived face quantities")
    return (
        face.lazy()
        .group_by(list(CELL_KEY_COLUMNS))
        .agg(
            pl.first("cell_x").alias("cell_x"),
            pl.first("cell_y").alias("cell_y"),
            pl.first("cell_volume").alias("cell_volume"),
            pl.first("radial_coordinate").alias("radial_coordinate"),
            pl.first("field_cell").alias("field_cell"),
            pl.first("runtime_grad_x").alias("runtime_grad_x"),
            pl.first("runtime_grad_y").alias("runtime_grad_y"),
            pl.len().alias("face_count"),
            pl.col("runtime_surface_x").sum().alias("sum_runtime_surface_x"),
            pl.col("runtime_surface_y").sum().alias("sum_runtime_surface_y"),
            pl.col("reconstructed_surface_x").sum().alias("sum_reconstructed_surface_x"),
            pl.col("reconstructed_surface_y").sum().alias("sum_reconstructed_surface_y"),
            pl.col("weighted_runtime_x").sum().alias("sum_weighted_runtime_x"),
            pl.col("weighted_runtime_y").sum().alias("sum_weighted_runtime_y"),
            pl.col("weighted_reconstructed_x").sum().alias("sum_weighted_reconstructed_x"),
            pl.col("weighted_reconstructed_y").sum().alias("sum_weighted_reconstructed_y"),
            pl.col("surface_delta_norm").max().alias("max_surface_delta_norm"),
            pl.col("field_face_delta").abs().max().alias("max_abs_field_face_delta"),
        )
        .with_columns(
            (pl.col("sum_weighted_runtime_x") / pl.col("cell_volume")).alias("pre_rz_grad_x"),
            (pl.col("sum_weighted_runtime_y") / pl.col("cell_volume")).alias("pre_rz_grad_y"),
            (pl.col("sum_runtime_surface_x") / pl.col("cell_volume")).alias("surface_balance_x"),
            (pl.col("sum_runtime_surface_y") / pl.col("cell_volume")).alias("surface_balance_y"),
        )
        .with_columns(
            pl.when(pl.lit(radial_component) == 0).then(pl.col("field_cell") / pl.col("radial_coordinate")).otherwise(0.0).alias("rz_correction_x"),
            pl.when(pl.lit(radial_component) == 1).then(pl.col("field_cell") / pl.col("radial_coordinate")).otherwise(0.0).alias("rz_correction_y"),
            pl.when(pl.lit(radial_component) == 0).then(1.0 / pl.col("radial_coordinate")).otherwise(0.0).alias("unit_rz_correction_x"),
            pl.when(pl.lit(radial_component) == 1).then(1.0 / pl.col("radial_coordinate")).otherwise(0.0).alias("unit_rz_correction_y"),
        )
        .with_columns(
            (pl.col("pre_rz_grad_x") - pl.col("rz_correction_x")).alias("reconstructed_grad_x"),
            (pl.col("pre_rz_grad_y") - pl.col("rz_correction_y")).alias("reconstructed_grad_y"),
            (pl.col("surface_balance_x") - pl.col("unit_rz_correction_x")).alias("surface_closure_x"),
            (pl.col("surface_balance_y") - pl.col("unit_rz_correction_y")).alias("surface_closure_y"),
        )
        .with_columns(
            (pl.col("runtime_grad_x") - pl.col("reconstructed_grad_x")).alias("gradient_delta_x"),
            (pl.col("runtime_grad_y") - pl.col("reconstructed_grad_y")).alias("gradient_delta_y"),
            ((pl.col("reconstructed_grad_x") ** 2 + pl.col("reconstructed_grad_y") ** 2).sqrt()).alias("reconstructed_grad_norm"),
            ((pl.col("runtime_grad_x") ** 2 + pl.col("runtime_grad_y") ** 2).sqrt()).alias("runtime_grad_norm"),
            ((pl.col("surface_closure_x") ** 2 + pl.col("surface_closure_y") ** 2).sqrt()).alias("surface_closure_norm"),
        )
        .with_columns(
            ((pl.col("gradient_delta_x") ** 2 + pl.col("gradient_delta_y") ** 2).sqrt()).alias("gradient_delta_norm")
        )
        .collect()
    )


__all__ = ["derive_cell_quantities", "derive_face_quantities"]
