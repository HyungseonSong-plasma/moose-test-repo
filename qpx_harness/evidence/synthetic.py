"""Synthetic numerical evidence fixtures for local and CI validation."""
from __future__ import annotations

import math

import polars as pl


def rz_constant_square_face_rows(
    *,
    run_id: str = "synthetic-run",
    case_id: str = "constant-rz",
    elem_id: int = 10,
    n0: float = 3.0,
    perturb_surface_x: float = 0.0,
    perturb_face_id: int = 1,
) -> pl.DataFrame:
    """Return face telemetry for an analytically exact constant RZ cell."""
    cell_x = 1.5
    cell_y = 0.5
    volume = 2.0 * math.pi * cell_x
    rows = [
        (0, 1.0, 0.5, -1.0, 0.0, 2.0 * math.pi * 1.0, -2.0 * math.pi, 0.0),
        (1, 2.0, 0.5, 1.0, 0.0, 2.0 * math.pi * 2.0, 4.0 * math.pi, 0.0),
        (2, 1.5, 0.0, 0.0, -1.0, 2.0 * math.pi * 1.5, 0.0, -3.0 * math.pi),
        (3, 1.5, 1.0, 0.0, 1.0, 2.0 * math.pi * 1.5, 0.0, 3.0 * math.pi),
    ]
    data: list[dict[str, object]] = []
    for face_id, face_x, face_y, nx, ny, coord_factor, sx, sy in rows:
        data.append(
            {
                "run_id": run_id,
                "case_id": case_id,
                "elem_id": elem_id,
                "face_id": face_id,
                "cell_x": cell_x,
                "cell_y": cell_y,
                "face_x": face_x,
                "face_y": face_y,
                "normal_x": nx,
                "normal_y": ny,
                "face_area": 1.0,
                "coord_factor": coord_factor,
                "moose_surface_x": sx
                + (perturb_surface_x if face_id == perturb_face_id else 0.0),
                "moose_surface_y": sy,
                "n_cell": n0,
                "n_face": n0,
                "cell_volume": volume,
                "radial_coordinate": cell_x,
                "qpx_grad_x": 0.0,
                "qpx_grad_y": 0.0,
            }
        )
    return pl.DataFrame(data)


__all__ = ["rz_constant_square_face_rows"]
