"""Stable constants and error contract for Issue43 coupling diagnostics."""
from pathlib import Path

from recipes import issue43_coupling_diagnostic as recipe

BASE_CASE_RELATIVE = Path("tests/Issue2_electron_bulk_drift/qvt_prepoisson")
DT_CONTROL = 1.0e-14
DT_FAIL = 1.0e-13
STEPS = 1
JACOBIAN_REL_TOL = 1.0e-6
DIAGNOSTIC_PETSC_OPTIONS = recipe.DIAGNOSTIC_PETSC_OPTIONS
JACOBIAN_PETSC_OPTIONS = recipe.JACOBIAN_PETSC_OPTIONS
RUNTIME_PURGE_DIRECTORY_NAMES = (".jitcache",)
RUNTIME_PURGE_PATTERNS = (
    "input_out*",
    "r43_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


class FastPlasmaCouplingDiagnosticError(RuntimeError):
    pass
