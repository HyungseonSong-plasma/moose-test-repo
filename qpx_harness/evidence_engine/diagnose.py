"""Conservative diagnosis helpers for constant-state Green-Gauss evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl


@dataclass(frozen=True)
class EvidenceTolerances:
    face_value_abs: float = 1.0e-14
    surface_vector_abs: float = 1.0e-14
    surface_closure_abs: float = 1.0e-14
    gradient_match_abs: float = 1.0e-12
    qpx_gradient_abs: float = 1.0e-12


def _max(frame: pl.DataFrame, column: str) -> float:
    value = frame.select(pl.col(column).abs().max()).item()
    return float(value or 0.0)


def summarize_constant_state(
    face: pl.DataFrame,
    cell: pl.DataFrame,
    *,
    tolerances: EvidenceTolerances = EvidenceTolerances(),
) -> dict[str, Any]:
    """Summarize the first evidence layer that fails a constant-state contract.

    The function deliberately stops short of declaring an RZ-specific atomic
    mechanism from magnitude agreement alone. That attribution requires spatial
    and component agreement with the MOOSE runtime path.
    """
    metrics = {
        "max_abs_n_face_delta": _max(face, "n_face_delta"),
        "max_surface_delta_norm": _max(face, "surface_delta_norm"),
        "max_surface_closure_norm": _max(cell, "surface_closure_norm"),
        "max_gradient_delta_norm": _max(cell, "gradient_delta_norm"),
        "max_qpx_grad_norm": _max(cell, "qpx_grad_norm"),
        "max_reconstructed_grad_norm": _max(cell, "reconstructed_grad_norm"),
    }

    if metrics["max_abs_n_face_delta"] > tolerances.face_value_abs:
        owner = "FACE_VALUE_RECONSTRUCTION"
        status = "ISOLATED_OWNER_CLASS"
    elif metrics["max_surface_delta_norm"] > tolerances.surface_vector_abs:
        owner = "SURFACE_VECTOR_CONSTRUCTION"
        status = "ISOLATED_OWNER_CLASS"
    elif metrics["max_surface_closure_norm"] > tolerances.surface_closure_abs:
        owner = "RZ_SURFACE_GEOMETRY_CLOSURE"
        status = "FAVORED"
    elif metrics["max_gradient_delta_norm"] > tolerances.gradient_match_abs:
        owner = "MISSING_MOOSE_ARITHMETIC_PATH"
        status = "UNRESOLVED"
    elif metrics["max_qpx_grad_norm"] > tolerances.qpx_gradient_abs:
        owner = "FV_GREEN_GAUSS_CELL_GRADIENT_CONSTANT_PRESERVATION"
        status = "ISOLATED_OWNER_CLASS"
    else:
        owner = None
        status = "CONSTANT_STATE_PASS"

    return {
        "status": status,
        "primary_owner_class": owner,
        "metrics": metrics,
        "rz_specific_status": "REQUIRES_SPATIAL_COMPONENT_AGREEMENT",
        "decision_order": [
            "face value reconstruction",
            "surface vector construction",
            "RZ surface/volume closure",
            "runtime-vs-reconstruction arithmetic path",
            "Green-Gauss constant preservation",
        ],
    }
