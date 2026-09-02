"""Issue43 coupling policy adapters over canonical diagnostic capabilities."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from recipes import issue43_coupling_diagnostic as recipe

from ..diagnostics import coupling as coupling_diagnostic
from ..diagnostics import jacobian as jacobian_diagnostic
from ..moose import log as moose_log
from ..petsc import jacobian as petsc_jacobian
from ..petsc import log as petsc_log
from .constants import (
    DIAGNOSTIC_PETSC_OPTIONS,
    JACOBIAN_PETSC_OPTIONS,
    JACOBIAN_REL_TOL,
)

_parse_variable_residuals = moose_log.parse_variable_residual_norms
_parse_scaling_factors = moose_log.parse_automatic_scaling_factors
_parse_pc_failure_reason = petsc_log.parse_pc_failure_reason
_parse_jacobian_tests = petsc_jacobian.parse_comparisons
_line_hits = coupling_diagnostic.line_hits


def recipe_backing_status() -> dict[str, bool]:
    return {
        "instrument-input": True,
        "diagnostic-options": DIAGNOSTIC_PETSC_OPTIONS is recipe.DIAGNOSTIC_PETSC_OPTIONS,
        "jacobian-options": JACOBIAN_PETSC_OPTIONS is recipe.JACOBIAN_PETSC_OPTIONS,
        "variable-residual-parser": _parse_variable_residuals
        is moose_log.parse_variable_residual_norms,
        "scaling-parser": _parse_scaling_factors
        is moose_log.parse_automatic_scaling_factors,
        "pc-failure-parser": _parse_pc_failure_reason is petsc_log.parse_pc_failure_reason,
        "jacobian-parser": _parse_jacobian_tests is petsc_jacobian.parse_comparisons,
        "runtime-failure-classifier": coupling_diagnostic.analyze_runtime_failure
        is coupling_diagnostic.analyze_runtime_failure,
    }


def analyze_jacobian_text(
    text: str, *, relative_tolerance: float = JACOBIAN_REL_TOL
) -> dict[str, Any]:
    """Issue43 tolerance adapter over the reusable Jacobian diagnostic owner."""
    return jacobian_diagnostic.analyze_comparisons(
        text,
        relative_tolerance=relative_tolerance,
    )


def analyze_log_text(text: str, *, returncode: int) -> dict[str, Any]:
    """Bind Issue43 coupled-variable identity to canonical runtime diagnostics."""
    return coupling_diagnostic.analyze_runtime_failure(
        text,
        returncode=returncode,
        coupled_scaling_variables=("n_e", "potential_plasma"),
    )


def analyze_log(log_path: Path, *, returncode: int) -> dict[str, Any]:
    if not log_path.is_file():
        return {
            "class": "DIAGNOSTIC_INSUFFICIENT",
            "reason": "runtime log is missing",
            "returncode": returncode,
        }
    return analyze_log_text(log_path.read_text(errors="replace"), returncode=returncode)


def analyze_jacobian_log(log_path: Path) -> dict[str, Any]:
    if not log_path.is_file():
        return {
            "status": "HOLD",
            "class": "JACOBIAN_EVIDENCE_INSUFFICIENT",
            "reason": "runtime log is missing",
            "relative_tolerance": JACOBIAN_REL_TOL,
            "tests": [],
        }
    return analyze_jacobian_text(log_path.read_text(errors="replace"))
