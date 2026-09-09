"""Concrete MOOSE/PETSc nonlinear runtime decoding at the solver boundary."""
from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from . import log as moose_log
from physics_harness.adapters.petsc import log as petsc_log


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
    """Extract the first stable MOOSE/PETSc nonlinear-failure signature."""
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


def artifact_failure_signature(result: Mapping[str, Any] | None) -> dict[str, Any]:
    if not result:
        return {"signature": "NO_RESULT"}
    evidence = result.get("evidence", {}) if isinstance(result, Mapping) else {}
    log = None
    if isinstance(evidence, Mapping):
        preferred = ("runtime_log", "solver_log", "log")
        values = [evidence.get(name) for name in preferred]
        values.extend(value for key, value in evidence.items() if str(key).endswith("_log"))
        for raw in values:
            if isinstance(raw, str):
                candidate = Path(raw)
                if candidate.is_file():
                    log = candidate
                    break
    text = log.read_text(errors="replace") if log else ""
    facts = failure_signature(text)
    facts["log"] = str(log) if log else None
    return facts


def runtime_core_facts(text: str, *, returncode: int, coupled_scaling_variables: Iterable[str] = ()) -> dict[str, Any]:
    residual_blocks = moose_log.parse_variable_residual_norms(text)
    scaling_blocks = moose_log.parse_automatic_scaling_factors(text)
    scaling = scaling_blocks[0] if scaling_blocks else {}
    linear_reason = petsc_log.first_failed_reason(petsc_log.parse_linear_solve_terminations(text))
    nonlinear_reason = petsc_log.first_failed_reason(petsc_log.parse_nonlinear_solve_terminations(text))
    pc_failure_reason = petsc_log.parse_pc_failure_reason(text)
    pc_hits = petsc_log.line_hits(text, (r"DIVERGED_PC_FAILED", r"DIVERGED_PCSETUP_FAILED", r"PC failed due to", r"zero pivot", r"factorization", r"PCSetUp.*fail"))
    factorization_hits = petsc_log.line_hits(text, (r"FACTOR_(?:NUMERIC|STRUCT)_ZEROPIVOT", r"zero pivot", r"factorization", r"MatFactor", r"PCSetUp.*fail"))
    nonfinite_residuals = [
        {"block": index, "variable": name, "value": repr(value)}
        for index, block in enumerate(residual_blocks) for name, value in block.items()
        if not math.isfinite(value)
    ]
    requested = tuple(str(name) for name in coupled_scaling_variables)
    scaling_invalid = [
        {"variable": name, "value": repr(scaling[name])}
        for name in requested if name in scaling and (not math.isfinite(scaling[name]) or scaling[name] == 0.0)
    ]
    selected = [abs(scaling[name]) for name in requested if name in scaling and math.isfinite(scaling[name]) and scaling[name] != 0.0]
    ratio = max(selected) / min(selected) if len(selected) == 2 else None
    return {
        "returncode": returncode, "linear_reason": linear_reason, "nonlinear_reason": nonlinear_reason,
        "pc_failure_reason": pc_failure_reason, "pc_hits": pc_hits, "factorization_hits": factorization_hits,
        "variable_residuals": residual_blocks, "nonfinite_residuals": nonfinite_residuals,
        "automatic_scaling_factors": scaling_blocks, "scaling_invalid": scaling_invalid,
        "scaling_factor_ratio": ratio,
    }


__all__ = [
    "FAILURE_PATTERNS",
    "artifact_failure_signature",
    "failure_signature",
    "runtime_core_facts",
]
