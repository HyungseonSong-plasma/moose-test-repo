"""Backend-neutral termination selection for already-decoded evidence rows."""
from __future__ import annotations

from typing import Any


def first_failed_reason(rows: list[dict[str, Any]]) -> str | None:
    """Return the first explicitly non-converged reason from decoded rows."""
    return next((str(row["reason"]) for row in rows if not row.get("converged")), None)


__all__ = ["first_failed_reason"]
