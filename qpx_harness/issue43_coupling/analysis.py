"""Pure Issue43 coupling diagnostic interpretation owner."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from recipes import issue43_coupling_diagnostic as recipe

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
    tests = _parse_jacobian_tests(text)
    if not tests:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_EVIDENCE_INSUFFICIENT",
            "reason": "PETSc -snes_test_jacobian produced no parseable Jacobian comparison",
            "relative_tolerance": relative_tolerance,
            "tests": [],
        }
    nonfinite = [
        item
        for item in tests
        if not math.isfinite(item["relative_frobenius_error"])
        or not math.isfinite(item["absolute_frobenius_error"])
    ]
    finite_relative = [
        item["relative_frobenius_error"]
        for item in tests
        if math.isfinite(item["relative_frobenius_error"])
    ]
    worst = max(finite_relative) if finite_relative else math.inf
    if nonfinite or worst > relative_tolerance:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_MISMATCH",
            "reason": (
                "assembled-vs-finite-difference Jacobian relative Frobenius error exceeds "
                f"the declared tolerance {relative_tolerance:g} or is non-finite"
            ),
            "relative_tolerance": relative_tolerance,
            "worst_relative_frobenius_error": worst,
            "nonfinite": nonfinite,
            "tests": tests,
        }
    return {
        "status": "PASS",
        "class": "JACOBIAN_CORRECTNESS_PASS",
        "reason": "all observed PETSc Jacobian comparisons satisfy the declared relative tolerance",
        "relative_tolerance": relative_tolerance,
        "worst_relative_frobenius_error": worst,
        "nonfinite": [],
        "tests": tests,
    }


def analyze_log_text(text: str, *, returncode: int) -> dict[str, Any]:
    residual_blocks = _parse_variable_residuals(text)
    scaling_blocks = _parse_scaling_factors(text)
    scaling = scaling_blocks[0] if scaling_blocks else {}

    linear_reason = None
    nonlinear_reason = None
    match = re.search(r"Linear solve did not converge due to\s+([A-Z0-9_]+)", text)
    if match:
        linear_reason = match.group(1)
    match = re.search(r"Nonlinear solve did not converge due to\s+([A-Z0-9_]+)", text)
    if match:
        nonlinear_reason = match.group(1)
    pc_failure_reason = _parse_pc_failure_reason(text)

    pc_hits = _line_hits(
        text,
        (
            r"DIVERGED_PC_FAILED",
            r"DIVERGED_PCSETUP_FAILED",
            r"PC failed due to",
            r"zero pivot",
            r"factorization",
            r"PCSetUp.*fail",
        ),
    )
    factorization_hits = _line_hits(
        text,
        (
            r"FACTOR_(?:NUMERIC|STRUCT)_ZEROPIVOT",
            r"zero pivot",
            r"factorization",
            r"MatFactor",
            r"PCSetUp.*fail",
        ),
    )

    nonfinite_residuals: list[dict[str, Any]] = []
    for index, block in enumerate(residual_blocks):
        for name, value in block.items():
            if not math.isfinite(value):
                nonfinite_residuals.append(
                    {"block": index, "variable": name, "value": repr(value)}
                )

    scaling_invalid: list[dict[str, Any]] = []
    for name in ("n_e", "potential_plasma"):
        if name not in scaling:
            continue
        value = scaling[name]
        if not math.isfinite(value) or value == 0.0:
            scaling_invalid.append({"variable": name, "value": repr(value)})

    selected_scaling = [
        abs(scaling[name])
        for name in ("n_e", "potential_plasma")
        if name in scaling and math.isfinite(scaling[name]) and scaling[name] != 0.0
    ]
    scaling_ratio = (
        max(selected_scaling) / min(selected_scaling)
        if len(selected_scaling) == 2
        else None
    )

    finite_residual_blocks = bool(residual_blocks) and not nonfinite_residuals
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
        "returncode": returncode,
        "linear_reason": linear_reason,
        "nonlinear_reason": nonlinear_reason,
        "pc_failure_reason": pc_failure_reason,
        "pc_hits": pc_hits,
        "factorization_hits": factorization_hits,
        "variable_residuals": residual_blocks,
        "nonfinite_residuals": nonfinite_residuals,
        "automatic_scaling_factors": scaling_blocks,
        "scaling_invalid": scaling_invalid,
        "scaling_factor_ratio_n_e_to_potential": scaling_ratio,
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
