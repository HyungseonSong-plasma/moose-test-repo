"""Canonical column contracts for numerical face/cell evidence.

The evidence engine treats MOOSE-emitted geometry and gradient values as runtime
truth and keeps independently reconstructed values in separate columns. This
makes arithmetic-path disagreements explicit instead of overwriting evidence.
"""
from __future__ import annotations

from collections.abc import Iterable

FACE_REQUIRED_COLUMNS = (
    "run_id",
    "case_id",
    "elem_id",
    "face_id",
    "cell_x",
    "cell_y",
    "face_x",
    "face_y",
    "normal_x",
    "normal_y",
    "face_area",
    "coord_factor",
    "moose_surface_x",
    "moose_surface_y",
    "n_cell",
    "n_face",
    "cell_volume",
    "radial_coordinate",
    "qpx_grad_x",
    "qpx_grad_y",
)

CELL_KEY_COLUMNS = ("run_id", "case_id", "elem_id")


def missing_columns(columns: Iterable[str], required: Iterable[str]) -> tuple[str, ...]:
    """Return required columns that are absent from *columns*, preserving order."""
    present = set(columns)
    return tuple(name for name in required if name not in present)


def require_columns(columns: Iterable[str], required: Iterable[str], *, context: str) -> None:
    """Raise a compact contract error when evidence columns are incomplete."""
    missing = missing_columns(columns, required)
    if missing:
        raise ValueError(f"{context} missing required columns: {', '.join(missing)}")
