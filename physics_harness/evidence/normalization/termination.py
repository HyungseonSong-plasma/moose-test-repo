"""Normalization helpers for already-decoded solver termination records."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


def first_failed_reason(records: Iterable[Mapping[str, Any]]) -> str | None:
    """Return the first non-converged reason while preserving legacy selection semantics."""
    for record in records:
        if not record.get("converged") and record.get("reason"):
            return str(record["reason"])
    return None


__all__ = ["first_failed_reason"]
