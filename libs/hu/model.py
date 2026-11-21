"""Source-bound Human Understandability measurements, without a guessed score."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re

_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"INVALID_{field.upper()}")


def _sha(value: str, field: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f"INVALID_{field.upper()}")


def _references(values: tuple[str, ...], field: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be a tuple")
    for value in values:
        _text(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"DUPLICATE_{field.upper()}")


@dataclass(frozen=True, slots=True)
class StructuralMetric:
    name: str
    value: int | float
    method: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.name, "metric_name")
        _text(self.method, "metric_method")
        if type(self.value) not in (int, float) or not isfinite(self.value) or self.value < 0:
            raise ValueError("INVALID_METRIC_VALUE")
        _references(self.evidence_ids, "metric_evidence_ids")


@dataclass(frozen=True, slots=True)
class HUObservation:
    """An actual binary evaluator response, not a model prediction."""

    evaluator_id: str
    question_id: str
    criterion: str
    positive: bool
    revision: str
    blob_sha: str

    def __post_init__(self) -> None:
        for name in ("evaluator_id", "question_id", "criterion"):
            _text(getattr(self, name), name)
        if type(self.positive) is not bool:
            raise TypeError("HU_OBSERVATION_MUST_BE_BINARY")
        _sha(self.revision, "observation_revision")
        _sha(self.blob_sha, "observation_blob_sha")


@dataclass(frozen=True, slots=True)
class HUInput:
    target_id: str
    revision: str
    blob_sha: str
    structural_metrics: tuple[StructuralMetric, ...] = ()
    observations: tuple[HUObservation, ...] = ()
    unknowns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.target_id, "target_id")
        _sha(self.revision, "revision")
        _sha(self.blob_sha, "blob_sha")
        if not isinstance(self.structural_metrics, tuple) or not all(
            isinstance(m, StructuralMetric) for m in self.structural_metrics
        ):
            raise TypeError("INVALID_STRUCTURAL_METRICS")
        if len({m.name for m in self.structural_metrics}) != len(self.structural_metrics):
            raise ValueError("DUPLICATE_STRUCTURAL_METRIC")
        if not isinstance(self.observations, tuple) or not all(
            isinstance(o, HUObservation) for o in self.observations
        ):
            raise TypeError("INVALID_HU_OBSERVATIONS")
        _references(self.unknowns, "unknowns")
        for observation in self.observations:
            if observation.revision != self.revision or observation.blob_sha != self.blob_sha:
                raise ValueError("HU_OBSERVATION_SOURCE_MISMATCH")


@dataclass(frozen=True, slots=True)
class ObservedHU:
    question_id: str
    criterion: str
    positive_count: int
    negative_count: int
    independent_evaluators: int
    positive_rate: float | None  # only with >=2 independent evaluators


@dataclass(frozen=True, slots=True)
class HUAssessment:
    target_id: str
    revision: str
    blob_sha: str
    structural_metrics: tuple[StructuralMetric, ...]
    observed: tuple[ObservedHU, ...]
    unknowns: tuple[str, ...]
    predicted_score: None = None  # deliberately not a structural-score proxy
