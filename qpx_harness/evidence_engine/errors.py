"""Machine-readable runtime error evidence owned by the unified evidence engine."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .provenance import artifact_created_utc

ERROR_LEDGER_SCHEMA_VERSION = 1


def error_record(
    *,
    stage: str,
    scope: str,
    message: str,
    error_type: str = "runtime_error",
    campaign_id: str | None = None,
    attempt_id: str | None = None,
    probe_id: str | None = None,
    phase_id: str | None = None,
    case_id: str | None = None,
    fatal: bool = False,
    exception: Exception | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one canonical machine-readable runtime-error evidence record."""
    record: dict[str, Any] = {
        "error_type": str(error_type),
        "stage": str(stage),
        "scope": str(scope),
        "fatal": bool(fatal),
        "message": str(message),
        "created_utc": artifact_created_utc(),
    }
    for key, value in (
        ("campaign_id", campaign_id),
        ("attempt_id", attempt_id),
        ("probe_id", probe_id),
        ("phase_id", phase_id),
        ("case_id", case_id),
    ):
        if value is not None:
            record[key] = str(value)
    if exception is not None:
        record["exception_type"] = type(exception).__name__
        record["exception_message"] = str(exception)
    if details:
        record["details"] = dict(details)
    return record


def merge_error_records(*record_groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge error record groups while preserving source order."""
    merged: list[dict[str, Any]] = []
    for group in record_groups:
        merged.extend(dict(record) for record in group)
    return merged


class ErrorLedger:
    """JSONL-backed append-only runtime-error evidence ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: list[dict[str, Any]] = []

    def __bool__(self) -> bool:
        return bool(self.records)

    def record(self, **kwargs: Any) -> dict[str, Any]:
        record = error_record(**kwargs)
        self.records.append(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record


__all__ = [
    "ERROR_LEDGER_SCHEMA_VERSION",
    "ErrorLedger",
    "error_record",
    "merge_error_records",
]
