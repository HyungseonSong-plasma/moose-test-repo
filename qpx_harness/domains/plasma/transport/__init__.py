"""Reusable plasma transport semantics.

Only scientific transport meaning belongs here. Source parsing and numerical
comparison live under observation/analysis responsibility owners.
"""
from __future__ import annotations

OXYGEN_HEAVY_SPECIES = ("O2", "O2s", "O2p", "O", "Om", "Op", "Os")
DMIX_EQUIVALENCE_REL_TOL = 2.0e-5
DMIX_TRACE_MASS_FRACTIONS = {
    "w_O2": 0.99994,
    "w_O2s": 1.0e-5,
    "w_O2p": 1.0e-5,
    "w_O": 1.0e-5,
    "w_Om": 1.0e-5,
    "w_Op": 1.0e-5,
    "w_Os": 1.0e-5,
}

__all__ = [
    "OXYGEN_HEAVY_SPECIES",
    "DMIX_EQUIVALENCE_REL_TOL",
    "DMIX_TRACE_MASS_FRACTIONS",
]
