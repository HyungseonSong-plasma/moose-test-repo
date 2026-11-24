"""Generic, revision-bound analysis output consumed by planning and reporting."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"INVALID_{name.upper()}")


def _unique_strings(values: tuple[str, ...], name: str) -> None:
    if not isinstance(values, tuple) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise TypeError(f"{name} must be nonempty strings in a tuple")
    if len(set(values)) != len(values):
        raise ValueError(f"DUPLICATE_{name.upper()}")


@dataclass(frozen=True, slots=True)
class AnalysisValue:
    name: str
    value: int | float
    method: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.name, "analysis_value_name")
        _nonempty(self.method, "analysis_value_method")
        if type(self.value) not in (int, float) or not isfinite(self.value):
            raise ValueError("INVALID_ANALYSIS_VALUE")
        _unique_strings(self.evidence_ids, "analysis_value_evidence_ids")


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    """Assessment + optional measured data, never an authorization."""

    name: str
    status: str  # MEASURED / OBSERVED / REVIEW_REQUIRED / UNVALIDATED
    summary: str
    evidence_ids: tuple[str, ...] = ()
    source_revision: str | None = None
    values: tuple[AnalysisValue, ...] = ()
    unknowns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.name, "assessment_name")
        if self.status not in {"MEASURED", "OBSERVED", "REVIEW_REQUIRED", "UNVALIDATED"}:
            raise ValueError("INVALID_ASSESSMENT_STATUS")
        _nonempty(self.summary, "assessment_summary")
        _unique_strings(self.evidence_ids, "assessment_evidence_ids")
        _unique_strings(self.unknowns, "assessment_unknowns")
        if self.source_revision is not None:
            _nonempty(self.source_revision, "assessment_source_revision")
        if not isinstance(self.values, tuple) or not all(isinstance(v, AnalysisValue) for v in self.values):
            raise TypeError("INVALID_ASSESSMENT_VALUES")
        if len({v.name for v in self.values}) != len(self.values):
            raise ValueError("DUPLICATE_ASSESSMENT_VALUE")
        if self.status == "MEASURED" and (not self.evidence_ids or not self.source_revision):
            raise ValueError("MEASURED_ASSESSMENT_REQUIRES_SOURCE")
