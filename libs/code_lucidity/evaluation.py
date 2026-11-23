"""Code-understandability indicators, optional human observations, and comparisons.

The engine calculates: contextual interpretation and choice belong to Analysis
and Planning. No outcome claims are inferred from structural indicators.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .metrics import derive_indicators
from .model import UnderstandabilityAssessment, UnderstandabilityInput, ObservedHumanResponse


def evaluate_understandability(sample: UnderstandabilityInput) -> UnderstandabilityAssessment:
    if not isinstance(sample, UnderstandabilityInput):
        raise TypeError("UNDERSTANDABILITY_INPUT_REQUIRED")
    groups = defaultdict(list)
    for observation in sample.observations:
        groups[(observation.criterion, observation.question_id)].append(observation)

    observed = []
    for (criterion, question_id), values in sorted(groups.items()):
        evaluators = {value.evaluator_id for value in values}
        if len(evaluators) != len(values):
            raise ValueError("DUPLICATE_HUMAN_EVALUATOR_FOR_QUESTION")
        positive = sum(value.positive for value in values)
        observed.append(ObservedHumanResponse(
            question_id=question_id, criterion=criterion,
            positive_count=positive, negative_count=len(values) - positive,
            independent_evaluators=len(evaluators),
            positive_rate=positive / len(values) if len(evaluators) >= 2 else None,
        ))

    unknowns = set(sample.unknowns)
    # Human observations are not a prerequisite for code metrics.
    return UnderstandabilityAssessment(
        target_id=sample.target_id, revision=sample.revision,
        blob_sha=sample.blob_sha, structural_metrics=sample.structural_metrics,
        observed=tuple(observed), unknowns=tuple(sorted(unknowns)),
        indicators=derive_indicators(
            sample.structural_metrics, source_facts=sample.source_facts,
        ),
    )


@dataclass(frozen=True, slots=True)
class MetricDifference:
    """Difference between source-comparable numeric measurements."""

    name: str
    before: int | float
    after: int | float
    difference: int | float


@dataclass(frozen=True, slots=True)
class UnderstandabilityComparison:
    """Descriptive differences; never evidence of improved comprehension."""

    before_revision: str
    after_revision: str
    metric_differences: tuple[MetricDifference, ...]
    unknowns: tuple[str, ...]
    improvement_proven: bool = False
    indicator_differences: tuple[MetricDifference, ...] = ()


def _numeric_differences(left, right, *, kind: str):
    before = {metric.name: metric for metric in left}
    after = {metric.name: metric for metric in right}
    differences = []
    unknowns = set()
    for name in sorted(before.keys() | after.keys()):
        a, b = before.get(name), after.get(name)
        if a is None or b is None or a.method != b.method:
            unknowns.add(f"INCOMPARABLE_UNDERSTANDABILITY_{kind}:{name}")
            continue
        differences.append(MetricDifference(name, a.value, b.value, b.value - a.value))
    return tuple(differences), unknowns


def compare_understandability(before: UnderstandabilityAssessment, after: UnderstandabilityAssessment) -> UnderstandabilityComparison:
    """Compare numeric measurements. Analysis decides their significance."""
    if not isinstance(before, UnderstandabilityAssessment) or not isinstance(after, UnderstandabilityAssessment):
        raise TypeError("UNDERSTANDABILITY_ASSESSMENTS_REQUIRED")
    if before.target_id != after.target_id:
        raise ValueError("UNDERSTANDABILITY_TARGET_MISMATCH")

    structural, unknown_metrics = _numeric_differences(
        before.structural_metrics, after.structural_metrics, kind="METRIC",
    )
    indicators, unknown_indicators = _numeric_differences(
        before.indicators, after.indicators, kind="INDICATOR",
    )
    unknowns = set(before.unknowns + after.unknowns)
    unknowns.update(unknown_metrics)
    unknowns.update(unknown_indicators)
    unknowns.add("STRUCTURAL_DELTA_NOT_UNDERSTANDABILITY_IMPROVEMENT_PROOF")
    return UnderstandabilityComparison(
        before_revision=before.revision, after_revision=after.revision,
        metric_differences=structural, unknowns=tuple(sorted(unknowns)),
        indicator_differences=indicators,
    )
