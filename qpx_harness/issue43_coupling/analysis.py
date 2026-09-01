"""Pure Issue43 coupling diagnostic interpretation owner."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from recipes import issue43_coupling_diagnostic as recipe

from ..diagnostics import jacobian as jacobian_diagnostic
from ..diagnostics import nonlinear_solver as nonlinear_diagnostic
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
    }


def _line_hits(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns)
    ]


def analyze_jacobian_text(
    text: str, *, relative_tolerance: float = JACOBIAN_REL_TOL
) -> dict[str, Any]:
    """Compatibility wrapper over the reusable Jacobian diagnostic owner."""
    return jacobian_diagnostic.analyze_comparisons(
        text,
        relative_tolerance=relative_tolerance,
    )


def analyze_log_text(text: str, *, returncode: int) -> dict[str, Any]:
    """Apply Issue43 hypothesis policy to reusable runtime diagnostic facts."""
    core = nonlinear_diagnostic.runtime_core_facts(
        text,
        returncode=returncode,
        coupled_scaling_variables=("n_e", "potential_plasma"),
    )
    linear_reason = core["linear_reason"]
    pc_failure_reason = core["pc_failure_reason"]
    pc_hits = core["pc_hits"]
    nonfinite_residuals = core["nonfinite_residuals"]
    scaling_invalid = core["scaling_invalid"]
    finite_residual_blocks = bool(core["variable_residuals"]) and not nonfinite_residuals

    if pc_hits or linear_reason in {"DIVERGED_PC_FAILED", "DIVERGED_PCSETUP_FAILED"}:
        decision_class = "PC_OR_FACTORIZATION_FAIL"
        if pc_failure_reason == "FACTOR_NUMERIC_ZEROPIVOT":
            reason = (
                "PETSc LU/preconditioner setup failed with FACTOR_NUMERIC_ZEROPIVOT; "
                "later nonlinear NAN/INF is downstream of the factorization failure"
            )
        else:
            reason = (
                "the first direct linear-solver signature is PETSc preconditioner/setup failure; "
                "later nonlinear NAN/INF is not promoted above that earlier failure"
            )
    elif nonfinite_residuals:
        decision_class = "INITIAL_NONFINITE_FAIL"
        reason = "variable-residual diagnostics contain NaN/Inf without an earlier PC failure"
    elif scaling_invalid:
        decision_class = "SCALING_DOMINATED_FAIL"
        reason = "automatic scaling produced a zero or non-finite factor for a coupled variable"
    elif returncode != 0 and finite_residual_blocks:
        decision_class = "COUPLED_JACOBIAN_OR_RESIDUAL_FAIL"
        reason = (
            "runtime failed with finite per-variable residual evidence and without a direct "
            "PC/non-finite/scaling-invalid signature"
        )
    else:
        decision_class = "DIAGNOSTIC_INSUFFICIENT"
        reason = "available diagnostic signatures do not uniquely identify H1-H4"

    return {
        "class": decision_class,
        "reason": reason,
        **core,
    }


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
