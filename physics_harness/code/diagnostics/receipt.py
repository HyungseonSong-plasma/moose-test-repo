"""Immutable exact-HEAD evidence and bounded collection coverage receipts."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from .collector import SourceRecord
from .request import ScanRequest, normalized_path


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
        if not isinstance(self.blob_sha, str) or len(self.blob_sha) != 40:
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

    def __post_init__(self) -> None:
        if self.completeness not in {"COMPLETE", "PARTIAL"}:
            raise ValueError("INVALID_RECEIPT_COMPLETENESS")
        if tuple(sorted(self.files, key=lambda f: f.path)) != self.files:
            raise ValueError("RECEIPT_FILES_NOT_SORTED")
        if len(set(f.path for f in self.files)) != len(self.files):
            raise ValueError("RECEIPT_DUPLICATE_PATH")
        if not isinstance(self.unresolved, tuple):
            raise TypeError("receipt.unresolved must be a tuple")
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
    )
