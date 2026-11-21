"""Aggregate actual HU observations; structural counts do not predict HU."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .model import HUAssessment, HUInput, ObservedHU


def evaluate_hu(sample: HUInput) -> HUAssessment:
    if not isinstance(sample, HUInput):
        raise TypeError("HU_INPUT_REQUIRED")
    groups = defaultdict(list)
    for observation in sample.observations:
        groups[(observation.criterion, observation.question_id)].append(observation)

    observed = []
    for (criterion, question_id), values in sorted(groups.items()):
        evaluators = {value.evaluator_id for value in values}
        if len(evaluators) != len(values):
            raise ValueError("DUPLICATE_HU_EVALUATOR_FOR_QUESTION")
        positive = sum(value.positive for value in values)
        observed.append(ObservedHU(
            question_id=question_id, criterion=criterion,
            positive_count=positive, negative_count=len(values) - positive,
            independent_evaluators=len(evaluators),
            positive_rate=positive / len(values) if len(evaluators) >= 2 else None,
        ))

    unknowns = set(sample.unknowns)
    if not sample.observations:
        unknowns.add("HUMAN_UNDERSTANDABILITY_NOT_OBSERVED")
    return HUAssessment(
        target_id=sample.target_id, revision=sample.revision,
        blob_sha=sample.blob_sha, structural_metrics=sample.structural_metrics,
        observed=tuple(observed), unknowns=tuple(sorted(unknowns)),
    )


@dataclass(frozen=True, slots=True)
class MetricDifference:
    """Observed change in a comparable structural metric."""

    name: str
    before: int | float
    after: int | float
    difference: int | float


@dataclass(frozen=True, slots=True)
class HUComparison:
    """Descriptive before/after change, never proof of improved comprehension."""

    before_revision: str
    after_revision: str
    metric_differences: tuple[MetricDifference, ...]
    unknowns: tuple[str, ...]
    improvement_proven: bool = False


def compare_hu(before: HUAssessment, after: HUAssessment) -> HUComparison:
    """Compare matching structural measurements without inferring HU improvement."""
    if not isinstance(before, HUAssessment) or not isinstance(after, HUAssessment):
        raise TypeError("HU_ASSESSMENTS_REQUIRED")
    if before.target_id != after.target_id:
        raise ValueError("HU_TARGET_MISMATCH")
    left = {metric.name: metric for metric in before.structural_metrics}
    right = {metric.name: metric for metric in after.structural_metrics}
    differences = []
    unknowns = set(before.unknowns + after.unknowns)
    for name in sorted(left.keys() | right.keys()):
        a, b = left.get(name), right.get(name)
        if a is None or b is None or a.method != b.method:
            unknowns.add(f"INCOMPARABLE_HU_METRIC:{name}")
            continue
        differences.append(MetricDifference(name, a.value, b.value, b.value - a.value))
    unknowns.add("STRUCTURAL_DELTA_NOT_HU_IMPROVEMENT_PROOF")
    return HUComparison(
        before_revision=before.revision, after_revision=after.revision,
        metric_differences=tuple(differences), unknowns=tuple(sorted(unknowns)),
    )
