"""PETSc-specific performance collection and raw log_view decoding."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any


def _number(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    text = value.strip()
    try:
        if re.fullmatch(r"[+-]?\d+", text):
            return int(text)
        return float(text)
    except ValueError:
        return value


def collect_log_view_csv(path: Path | None) -> dict[str, Any] | None:
    """Decode PETSc ``-log_view :FILE:ascii_csv`` output into canonical rows."""
    if path is None or not path.is_file():
        return None
    rows: list[dict[str, Any]] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if any(value not in (None, "") for value in row.values()):
                rows.append({k: _number(v) for k, v in row.items() if k is not None})
    return {"format": "petsc_log_view_ascii_csv", "rows": rows}


def load_events(path: Path) -> dict[str, dict[str, float]]:
    """Return rank-zero PETSc event timing facts from log_view CSV."""
    events: dict[str, dict[str, float]] = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("Rank") not in (None, "", "0"):
                continue
            name = row.get("Event Name", "")
            if not name:
                continue
            try:
                events[name] = {
                    "count": float(row.get("Count") or 0),
                    "time": float(row.get("Time") or 0),
                }
            except ValueError:
                continue
    return events


def event_time(events: dict[str, dict[str, float]], name: str) -> float:
    return events.get(name, {}).get("time", 0.0)


def profile_arguments(csv_path: Path) -> list[str]:
    """Return PETSc raw profiling arguments owned by the PETSc adapter."""
    return [
        "-log_view",
        f":{csv_path}:ascii_csv",
        "-log_view_memory",
        "-snes_monitor",
        "-snes_converged_reason",
        "-ksp_converged_reason",
    ]


def event_hints(csv_path: Path) -> list[dict[str, str]]:
    """Extract solver-performance event hints without assigning bottleneck policy."""
    if not csv_path.is_file():
        return []
    wanted = re.compile(
        r"KSPSolve|SNES|PCSetUp|MatLUFactor|MatCholeskyFactor|MatAssembly|MatSolve|Factor",
        re.IGNORECASE,
    )
    hits: list[dict[str, str]] = []
    try:
        with csv_path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                joined = " ".join(str(value) for value in row.values())
                if wanted.search(joined):
                    hits.append({k: v for k, v in row.items() if v not in (None, "")})
    except Exception:
        return []
    return hits[:80]


EVENT_SNES_SOLVE = "SNESSolve"
EVENT_JACOBIAN_EVAL = "SNESJacobianEval"
EVENT_FUNCTION_EVAL = "SNESFunctionEval"
EVENT_PC_SETUP = "PCSetUp"
EVENT_KSP_SOLVE = "KSPSolve"
EVENT_LU_NUMERIC = "MatLUFactorNum"
EVENT_LU_SYMBOLIC = "MatLUFactorSym"
EVENT_MATRIX_ASSEMBLY_END = "MatAssemblyEnd"

__all__ = [
    "EVENT_FUNCTION_EVAL", "EVENT_JACOBIAN_EVAL", "EVENT_KSP_SOLVE",
    "EVENT_LU_NUMERIC", "EVENT_LU_SYMBOLIC", "EVENT_MATRIX_ASSEMBLY_END",
    "EVENT_PC_SETUP", "EVENT_SNES_SOLVE", "collect_log_view_csv", "event_hints",
    "event_time", "load_events", "profile_arguments",
]
