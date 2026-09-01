"""Reusable PETSc termination selection mechanics."""
from __future__ import annotations

from typing import Any

from ..petsc import log as petsc_log


def first_failed_reason(rows: list[dict[str, Any]]) -> str | None:
    """Return the first explicitly non-converged reason from parsed termination rows."""
    return next((str(row["reason"]) for row in rows if not row.get("converged")), None)


def first_linear_termination(text: str) -> dict[str, Any] | None:
    """Return the first parsed linear termination row, if observable."""
    rows = petsc_log.parse_linear_solve_terminations(text)
    return dict(rows[0]) if rows else None
