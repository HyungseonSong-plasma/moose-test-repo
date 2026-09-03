"""Synthetic numerical evidence fixtures for local and CI validation.

These fixtures are intentionally small and analytical. They validate the
Polars/DuckDB evidence pipeline without requiring a QPX executable or a MOOSE
build. The canonical fixture is one unit-area RZ cell with symmetry axis Y,
radial coordinate X, and a constant scalar field.
"""
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
    """Return face telemetry for an analytically exact constant RZ cell.

    Geometry contract:

    - symmetry/axial axis: Y
    - radial coordinate: X
    - cell: x in [1, 2], y in [0, 1]
    - cell centroid/radius: x = 1.5
    - 2-D area: 1
    - RZ volume: 2*pi*1.5

    ``perturb_surface_x`` modifies only the MOOSE-truth surface-vector X
    component on ``perturb_face_id``. This gives local tests a deterministic
    way to verify surface-vector fault isolation.
    """
    cell_x = 1.5
    cell_y = 0.5
    volume = 2.0 * math.pi * cell_x
    rows = [
        # face_id, face_x, face_y, nx, ny, coord_factor, Sx, Sy
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
