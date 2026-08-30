"""Reusable PETSc matrix-difference parsing and owner-block aggregation."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any


_FLOAT = r"[+\-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|nan|inf(?:inity)?)"


class MatrixParseError(ValueError):
    """Raised when a requested PETSc matrix artifact is missing or malformed."""


def parse_threshold_difference_matrix(text: str) -> dict[str, Any]:
    """Parse PETSc's thresholded hand-coded-minus-FD matrix section."""
    header = re.search(
        rf"Hand-coded minus finite-difference Jacobian with tolerance\s+({_FLOAT})\s+-+",
        text,
        re.IGNORECASE,
    )
    if not header:
        raise MatrixParseError("thresholded Jacobian-difference matrix header is missing")
    try:
        threshold = float(header.group(1))
    except ValueError as exc:
        raise MatrixParseError("invalid Jacobian-difference threshold") from exc

    tail = text[header.end() :]
    stop_patterns = (
        r"(?m)^\s*KSP Object:",
        r"(?m)^\s*Linear solve ",
        r"(?m)^\s*Nonlinear solve ",
        r"(?m)^\s*\|residual\|_2 of individual variables:",
        r"(?m)^\s*-+ Testing Jacobian",
    )
    stop = len(tail)
    for pattern in stop_patterns:
        match = re.search(pattern, tail)
        if match:
            stop = min(stop, match.start())
    section = tail[:stop]

    entries: list[dict[str, Any]] = []
    row_pattern = re.compile(r"(?m)^\s*row\s+(\d+)\s*:\s*(.*)$", re.IGNORECASE)
    entry_pattern = re.compile(rf"\((\d+)\s*,\s*({_FLOAT})\)", re.IGNORECASE)
    for row_match in row_pattern.finditer(section):
        row = int(row_match.group(1))
        row_text = row_match.group(2)
        for entry_match in entry_pattern.finditer(row_text):
            try:
                value = float(entry_match.group(2))
            except ValueError:
                value = math.nan
            entries.append({"row": row, "col": int(entry_match.group(1)), "value": value})
    return {"threshold": threshold, "entries": entries, "section_observed": True}


def summarize_by_owner(
    difference: Mapping[str, Any],
    owner_by_dof: Mapping[int, str],
) -> dict[str, Any]:
    """Aggregate matrix-difference entries by caller-provided row/column ownership.

    This function reports facts only. It does not assign scientific categories or
    decide whether any block is acceptable, dominant, or causally meaningful.
    """
    blocks: dict[str, dict[str, Any]] = {}
    unmapped: list[dict[str, Any]] = []
    total_energy = 0.0
    entries = difference.get("entries", [])
    if not isinstance(entries, list):
        raise MatrixParseError("difference.entries must be a list")

    for entry in entries:
        if not isinstance(entry, Mapping):
            unmapped.append({"entry": entry, "row_variable": None, "col_variable": None})
            continue
        row = entry.get("row")
        col = entry.get("col")
        raw_value = entry.get("value")
        row_var = owner_by_dof.get(row) if isinstance(row, int) else None
        col_var = owner_by_dof.get(col) if isinstance(col, int) else None
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = math.nan
        if row_var is None or col_var is None or not math.isfinite(value):
            unmapped.append(
                {
                    **dict(entry),
                    "row_variable": row_var,
                    "col_variable": col_var,
                }
            )
            continue

        energy = value * value
        total_energy += energy
        key = f"{row_var}->{col_var}"
        block = blocks.setdefault(
            key,
            {
                "row_variable": row_var,
                "col_variable": col_var,
                "count": 0,
                "sum_squared_difference": 0.0,
                "max_abs_difference": 0.0,
            },
        )
        block["count"] += 1
        block["sum_squared_difference"] += energy
        block["max_abs_difference"] = max(block["max_abs_difference"], abs(value))

    for block in blocks.values():
        block["l2_difference"] = math.sqrt(block["sum_squared_difference"])

    return {
        "blocks": blocks,
        "unmapped_entries": unmapped,
        "entry_count": len(entries),
        "mapped_entry_count": sum(block["count"] for block in blocks.values()),
        "thresholded_l2_difference": math.sqrt(total_energy),
    }
