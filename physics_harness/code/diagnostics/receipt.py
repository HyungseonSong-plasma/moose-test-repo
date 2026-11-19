"""Immutable exact-HEAD evidence and bounded collection coverage receipts."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from collections.abc import Sequence

from .collector import SourceRecord
from .request import ScanBudget, ScanRequest, normalized_path


FILE_STATUSES = frozenset({
    "SCANNED", "UNSUPPORTED", "FAILED", "SKIPPED_BUDGET",
    "EXCLUDED", "UNRESOLVED",
})


@dataclass(frozen=True, slots=True)
class FileCoverage:
    path: str
    blob_sha: str
    status: str
    collectors: tuple[str, ...] = ()
    details: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_path(self.path)
        if (not isinstance(self.blob_sha, str) or len(self.blob_sha) != 40
                or any(ch not in "0123456789abcdef" for ch in self.blob_sha)):
            raise ValueError("FILE_RECEIPT_BLOB_REQUIRED")
        if self.status not in FILE_STATUSES:
            raise ValueError("UNKNOWN_FILE_COVERAGE_STATUS")
        if (not isinstance(self.collectors, tuple) or not isinstance(self.details, tuple)
                or any(not isinstance(v, str) for v in (*self.collectors, *self.details))):
            raise ValueError("INVALID_RECEIPT_VALUES")


@dataclass(frozen=True, slots=True)
class EvidenceReceipt:
    repository: str
    revision: str
    scope_id: str
    requested_includes: tuple[str, ...]
    requested_excludes: tuple[str, ...]
    collector_versions: tuple[tuple[str, str], ...]
    files: tuple[FileCoverage, ...]
    completeness: str
    unresolved: tuple[str, ...] = ()
    budget: ScanBudget | None = None
    attempted_files: int = 0
    read_bytes: int = 0
    elapsed_seconds: float = field(default=0.0, compare=False)

    def __post_init__(self) -> None:
        if self.completeness not in {"COMPLETE", "PARTIAL"}:
            raise ValueError("INVALID_RECEIPT_COMPLETENESS")
        if tuple(sorted(self.files, key=lambda f: f.path)) != self.files:
            raise ValueError("RECEIPT_FILES_NOT_SORTED")
        if len(set(f.path for f in self.files)) != len(self.files):
            raise ValueError("RECEIPT_DUPLICATE_PATH")
        if not isinstance(self.unresolved, tuple):
            raise TypeError("receipt.unresolved must be a tuple")
        if self.budget is not None and not isinstance(self.budget, ScanBudget):
            raise TypeError("receipt.budget must be a ScanBudget")
        for name in ("attempted_files", "read_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"INVALID_RECEIPT_COUNTER:{name}")
        if not isinstance(self.elapsed_seconds, (int, float)) or (
            not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0
        ):
            raise ValueError("INVALID_RECEIPT_DURATION")
        eligible = [f for f in self.files if f.status != "EXCLUDED"]
        if self.completeness == "COMPLETE" and (
            not eligible or any(f.status != "SCANNED" for f in eligible)
            or self.unresolved
        ):
            raise ValueError("FALSE_COMPLETE_RECEIPT")

    @property
    def scanned_count(self) -> int:
        return sum(item.status == "SCANNED" for item in self.files)

    @property
    def included_count(self) -> int:
        return sum(item.status != "EXCLUDED" for item in self.files)


def create_receipt(
    request: ScanRequest,
    *,
    scope_id: str,
    files: Sequence[FileCoverage],
    collector_versions: tuple[tuple[str, str], ...],
    unresolved: tuple[str, ...] = (),
    attempted_files: int = 0,
    read_bytes: int = 0,
    elapsed_seconds: float = 0.0,
) -> EvidenceReceipt:
    records = tuple(sorted(files, key=lambda f: f.path))
    unique_unresolved = tuple(sorted(set(unresolved)))
    eligible = [item for item in records if item.status != "EXCLUDED"]
    complete = (
        bool(eligible) and all(item.status == "SCANNED" for item in eligible)
        and not unique_unresolved
    )
    return EvidenceReceipt(
        repository=request.repository,
        revision=request.revision,
        scope_id=scope_id,
        requested_includes=request.includes,
        requested_excludes=request.excludes,
        collector_versions=collector_versions,
        files=records,
        completeness="COMPLETE" if complete else "PARTIAL",
        unresolved=unique_unresolved,
        budget=request.budget, attempted_files=attempted_files,
        read_bytes=read_bytes, elapsed_seconds=elapsed_seconds,
    )
