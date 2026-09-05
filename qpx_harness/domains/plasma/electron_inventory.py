"""Reusable electron-inventory closure semantics for plasma models."""
from __future__ import annotations


class ElectronInventoryNullspaceError(RuntimeError):
    """Electron-inventory closure or validation contract failure."""


DEFAULT_MACRO_ELECTRON_AVG = 1.0e16
C0_TARGET = 1.0e16
C1_TARGET = 1.01e16
CLOSURE_TARGET_REL_TOL = 1.0e-6
CLOSURE_DELTA_REL_TOL = 5.0e-4
INVENTORY_CONSISTENCY_REL_TOL = 1.0e-8
EXPECTED_DRIFT_BOUNDARIES = frozenset({
    "inlet", "outlet", "plasma_electrode", "plasma_metal", "plasma_right",
    "plasma_cover", "plasma_wafer", "plasma_focus_ring",
})
EXPECTED_POISSON_GROUNDS = frozenset({
    "plasma_metal", "plasma_electrode", "plasma_right", "inlet", "outlet",
})

__all__ = [
    "ElectronInventoryNullspaceError",
    "DEFAULT_MACRO_ELECTRON_AVG", "C0_TARGET", "C1_TARGET",
    "CLOSURE_TARGET_REL_TOL", "CLOSURE_DELTA_REL_TOL",
    "INVENTORY_CONSISTENCY_REL_TOL", "EXPECTED_DRIFT_BOUNDARIES",
    "EXPECTED_POISSON_GROUNDS",
]
