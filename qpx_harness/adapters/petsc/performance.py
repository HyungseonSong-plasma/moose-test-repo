"""PETSc-specific performance collection and raw-event decoding."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping

_EVENT_FACTS = {
    "snes_solve": "SNESSolve",
    "jacobian_eval": "SNESJacobianEval",
    "residual_eval": "SNESFunctionEval",
    "pc_setup": "PCSetUp",
    "linear_solve": "KSPSolve",
    "lu_numeric": "MatLUFactorNum",
    "lu_symbolic": "MatLUFactorSym",
    "matrix_assembly_end": "MatAssemblyEnd",
}


def _number(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    text = value.strip()
    try:
        if text.lstrip("+-").isdigit():
            return int(text)
        return float(text)
    except ValueError:
        return value


def collect_log_view_csv(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    rows: list[dict[str, Any]] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if any(value not in (None, "") for value in row.values()):
                rows.append({key: _number(value) for key, value in row.items() if key is not None})
    return {"format": "petsc_log_view_ascii_csv", "rows": rows}


def load_events(path: Path) -> dict[str, dict[str, float]]:
    events: dict[str, dict[str, float]] = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("Rank") not in (None, "", "0"):
                continue
            name = row.get("Event Name", "")
            if not name:
                continue
            try:
                events[name] = {"count": float(row.get("Count") or 0), "time": float(row.get("Time") or 0)}
            except ValueError:
                continue
    return events


def event_time(events: Mapping[str, Mapping[str, float]], name: str) -> float:
    return float(events.get(name, {}).get("time", 0.0))


def decode_timing_facts(path: Path) -> dict[str, float]:
    """Decode raw PETSc event names into backend-neutral timing fact keys."""
    events = load_events(path)
    return {key: event_time(events, event) for key, event in _EVENT_FACTS.items()}


def diagnostic_options(csv_path: Path) -> tuple[str, ...]:
    return (
        f"-log_view :{csv_path}:ascii_csv",
        "-log_view_memory",
        "-snes_monitor",
        "-snes_converged_reason",
        "-ksp_converged_reason",
    )


__all__ = ["collect_log_view_csv", "decode_timing_facts", "diagnostic_options", "event_time", "load_events"]
