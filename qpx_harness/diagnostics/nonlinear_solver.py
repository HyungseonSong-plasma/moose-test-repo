"""Reusable MOOSE/PETSc runtime solver facts with caller-owned interpretation."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Iterable

from ..moose import log as moose_log
from ..petsc import log as petsc_log
from .termination import first_failed_reason


FAILURE_PATTERNS = (
    ("DIVERGED_MAX_IT", r"DIVERGED_MAX_IT(?:\s+iterations\s+(\d+))?"),
    ("DIVERGED_LINE_SEARCH", r"DIVERGED_LINE_SEARCH"),
    ("DIVERGED_FNORM_NAN", r"DIVERGED_FNORM_NAN|NaN"),
    (
        "NONLINEAR_DID_NOT_CONVERGE",
        r"Nonlinear solve did not converge|Solve Did NOT Converge",
    ),
)


def failure_signature(text: str) -> dict[str, Any]:
    """Extract the first stable nonlinear-failure signature from runtime text."""

    for name, pattern in FAILURE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        iterations = None
        if match.lastindex and match.group(1):
            try:
                iterations = int(match.group(1))
            except ValueError:
                pass
        return {"signature": name, "iterations": iterations}
    return {"signature": None, "iterations": None}


def measurement_failure_signature(
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Read a PF result's preferred runtime log and return diagnostic facts."""

    if not result:
        return {"signature": "NO_RESULT"}
    evidence = result.get("evidence", {})
    log_raw = evidence.get("p3_log") or evidence.get("p2_log")
    log = Path(log_raw) if isinstance(log_raw, str) else None
    text = log.read_text(errors="replace") if log and log.is_file() else ""
    facts = failure_signature(text)
    facts["log"] = str(log) if log else None
    return facts


def runtime_core_facts(
    text: str,
    *,
    returncode: int,
    coupled_scaling_variables: Iterable[str] = (),
) -> dict[str, Any]:
    """Extract invariant first-failure, residual, scaling, and PC facts.

    No issue hypothesis is selected here. Callers supply any scaling variables whose
    ratio is meaningful for their own interpretation.
    """
    residual_blocks = moose_log.parse_variable_residual_norms(text)
    scaling_blocks = moose_log.parse_automatic_scaling_factors(text)
    scaling = scaling_blocks[0] if scaling_blocks else {}
    linear_reason = first_failed_reason(petsc_log.parse_linear_solve_terminations(text))
    nonlinear_reason = first_failed_reason(petsc_log.parse_nonlinear_solve_terminations(text))
    pc_failure_reason = petsc_log.parse_pc_failure_reason(text)

    pc_hits = petsc_log.line_hits(
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
    factorization_hits = petsc_log.line_hits(
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

    requested = tuple(str(name) for name in coupled_scaling_variables)
    scaling_invalid: list[dict[str, Any]] = []
    for name in requested:
        if name not in scaling:
            continue
        value = scaling[name]
        if not math.isfinite(value) or value == 0.0:
            scaling_invalid.append({"variable": name, "value": repr(value)})

    selected_scaling = [
        abs(scaling[name])
        for name in requested
        if name in scaling and math.isfinite(scaling[name]) and scaling[name] != 0.0
    ]
    scaling_ratio = (
        max(selected_scaling) / min(selected_scaling)
        if len(selected_scaling) == 2
        else None
    )

    return {
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
        "scaling_factor_ratio": scaling_ratio,
    }
