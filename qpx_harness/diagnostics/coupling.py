"""Reusable coupled nonlinear-solver failure classification facts.

This module owns issue-agnostic interpretation of MOOSE/PETSc runtime facts.
Experiment owners remain responsible for choosing coupled variables and deciding
what scientific hypothesis follows from these diagnostic classes.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from . import nonlinear_solver as nonlinear_diagnostic


def line_hits(text: str, patterns: tuple[str, ...]) -> list[str]:
    """Return stripped lines matching any case-insensitive regular expression."""
    return [
        line.strip()
        for line in text.splitlines()
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns)
    ]


def analyze_runtime_failure(
    text: str,
    *,
    returncode: int,
    coupled_scaling_variables: Iterable[str] = (),
) -> dict[str, Any]:
    """Classify invariant coupled-solver failure signatures.

    The classes deliberately stop at observable solver/runtime facts.  They do
    not select an experiment hypothesis or attach issue-specific causality.
    """
    core = nonlinear_diagnostic.runtime_core_facts(
        text,
        returncode=returncode,
        coupled_scaling_variables=coupled_scaling_variables,
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
                "the earliest direct linear-solver signature is PETSc "
                "preconditioner/setup failure"
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
        reason = "available invariant diagnostic signatures do not select a unique failure class"

    return {
        "class": decision_class,
        "reason": reason,
        **core,
    }
