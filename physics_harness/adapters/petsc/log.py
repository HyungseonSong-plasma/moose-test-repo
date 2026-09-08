"""Issue-agnostic PETSc/SNES/KSP termination parsing."""
from __future__ import annotations

import re
from typing import Any


def _parse_terminations(text: str, solve_kind: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        rf"(?m)^\s*{re.escape(solve_kind)} solve\s+(converged|did not converge)\s+due to\s+([A-Z0-9_]+)(?:\s+iterations\s+(\d+))?",
        re.IGNORECASE,
    )
    rows: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        rows.append(
            {
                "converged": match.group(1).lower() == "converged",
                "reason": match.group(2).upper(),
                "iterations": int(match.group(3)) if match.group(3) is not None else None,
            }
        )
    return rows


def parse_linear_solve_terminations(text: str) -> list[dict[str, Any]]:
    return _parse_terminations(text, "Linear")


def parse_nonlinear_solve_terminations(text: str) -> list[dict[str, Any]]:
    return _parse_terminations(text, "Nonlinear")


def first_failed_reason(rows: list[dict[str, Any]]) -> str | None:
    """Return the first explicitly non-converged reason from decoded PETSc rows."""
    return next((str(row["reason"]) for row in rows if not row.get("converged")), None)


def first_linear_termination(text: str) -> dict[str, Any] | None:
    """Return the first decoded PETSc linear termination row, if observable."""
    rows = parse_linear_solve_terminations(text)
    return dict(rows[0]) if rows else None


def parse_pc_failure_reason(text: str) -> str | None:
    match = re.search(r"PC failed due to\s+([A-Z0-9_]+)", text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def parse_petsc_version(text: str) -> str | None:
    for pattern in (
        r"PETSc(?:\s+Release)?\s+Version\s*[:=]?\s*([0-9]+\.[0-9]+\.[0-9]+)",
        r"PETSC_VERSION\s*[:=]\s*([0-9]+\.[0-9]+\.[0-9]+)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def line_hits(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns)
    ]


__all__ = [
    "first_failed_reason",
    "first_linear_termination",
    "line_hits",
    "parse_linear_solve_terminations",
    "parse_nonlinear_solve_terminations",
    "parse_pc_failure_reason",
    "parse_petsc_version",
]
