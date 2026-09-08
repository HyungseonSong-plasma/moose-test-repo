"""Execution-status interpretation for the R3 electron master diagnostic.

Scientific operator evidence is deliberately separated from nonlinear/linear
solver termination so a small constant-preservation floor is not conflated
with a physically incorrect operator.
"""
from __future__ import annotations

import math
from typing import Any

from .spec import CaseSpec

LINEAR_REFERENCE_N0 = 1.0e16
OPERATOR_FLOOR_ABS = 1.0e-8
LINEAR_REFERENCE_REL_TOL = 1.0e-12


def linear_reference_checker(observables: dict[str, Any]) -> dict[str, Any]:
    """Check constant preservation for the independent LinearFVDiffusion pair."""
    row = observables.get("last_row", {})
    keys = ("n_avg", "n_min", "n_max")
    if not all(isinstance(row.get(key), (int, float)) for key in keys):
        return {"pass": False, "error": "linear reference CSV lacks n_avg/n_min/n_max"}
    values = [float(row[key]) for key in keys]
    if not all(math.isfinite(value) for value in values):
        return {"pass": False, "error": "linear reference produced non-finite constant-state observables"}
    max_abs_error = max(abs(value - LINEAR_REFERENCE_N0) for value in values)
    relative_error = max_abs_error / LINEAR_REFERENCE_N0
    relative_spread = abs(values[2] - values[1]) / LINEAR_REFERENCE_N0
    return {
        "pass": relative_error <= LINEAR_REFERENCE_REL_TOL and relative_spread <= LINEAR_REFERENCE_REL_TOL,
        "n0": LINEAR_REFERENCE_N0,
        "max_abs_error": max_abs_error,
        "relative_error": relative_error,
        "relative_spread": relative_spread,
    }


def operator_status(
    spec: CaseSpec,
    *,
    electron_residuals: list[float],
    checker: dict[str, Any],
) -> str:
    """Return a scientific operator status independent of solver convergence."""
    if spec.base == "LINEAR_REF":
        if checker.get("pass") is True:
            err = float(checker.get("max_abs_error", 0.0))
            return "EXACT_CONSTANT" if err == 0.0 else "CONSTANT_PRESERVED_WITHIN_TOL"
        return "CONSTANT_DRIFT"

    if not electron_residuals:
        return "UNAVAILABLE"
    peak = max(abs(float(value)) for value in electron_residuals)
    if peak == 0.0:
        return "EXACT_ZERO"
    if peak <= OPERATOR_FLOOR_ABS:
        return "NUMERICAL_FLOOR_CANDIDATE"
    return "NONZERO_RESIDUAL"


def solver_status(
    *,
    returncode: int,
    timed_out: bool,
    failure: dict[str, Any],
    checker: dict[str, Any],
) -> str:
    """Return execution/solver termination independently of operator magnitude."""
    if timed_out:
        return "TIMEOUT"
    if returncode == 0 and checker.get("pass") is True:
        return "CONVERGED"
    signature = failure.get("signature")
    if signature:
        return str(signature)
    if returncode == 0:
        return "CHECKER_FAIL"
    return "RUNTIME_FAIL"
