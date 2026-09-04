"""Compatibility facade for canonical Green-Gauss validation policy."""
from __future__ import annotations

from qpx_harness.validation.green_gauss import (
    EvidenceTolerances as CanonicalEvidenceTolerances,
    build_constant_state_metrics as _build_canonical_metrics,
    build_constant_state_ruleset as _build_canonical_ruleset,
)

from ..models import (
    DiagnosticMetricSpec,
    DiagnosisRule,
    DiagnosisRuleRegistry,
    EvidenceTolerances,
    MetricPredicate,
    Z3OwnerRule,
    Z3RuleSet,
)


def _canonical_tolerances(
    tolerances: EvidenceTolerances | None,
) -> CanonicalEvidenceTolerances | None:
    if tolerances is None:
        return None
    return CanonicalEvidenceTolerances(**tolerances.model_dump())


def build_constant_state_registry(
    tolerances: EvidenceTolerances | None = None,
) -> DiagnosisRuleRegistry:
    """Project canonical validation policy into the historical registry DTOs."""
    canonical_metrics = _build_canonical_metrics()
    canonical_ruleset = _build_canonical_ruleset(_canonical_tolerances(tolerances))
    metrics = {
        metric_id: DiagnosticMetricSpec(**metric.model_dump())
        for metric_id, metric in canonical_metrics.items()
    }
    rules: list[DiagnosisRule] = []
    for rule in canonical_ruleset.rules:
        if len(rule.all_of) != 1 or rule.any_of or rule.none_of:
            raise ValueError(
                f"legacy DiagnosisRule projection requires one all_of predicate: {rule.rule_id}"
            )
        predicate = rule.all_of[0]
        if predicate.operator != "gt":
            raise ValueError(
                f"legacy DiagnosisRule projection requires gt predicate: {rule.rule_id}"
            )
        rules.append(
            DiagnosisRule(
                rule_id=rule.rule_id,
                metric_id=predicate.metric_id,
                threshold=predicate.threshold,
                owner_class=rule.owner_class,
                status=rule.status,
                decision_label=rule.decision_label,
                priority=rule.priority,
            )
        )
    return DiagnosisRuleRegistry(
        metrics=metrics,
        rules=tuple(rules),
        pass_status=canonical_ruleset.pass_status,
        rz_specific_status="REQUIRES_SPATIAL_COMPONENT_AGREEMENT",
    )


def build_constant_state_ruleset(
    tolerances: EvidenceTolerances | None = None,
) -> Z3RuleSet:
    """Project canonical backend-neutral rules into the historical Z3 DTOs."""
    canonical = _build_canonical_ruleset(_canonical_tolerances(tolerances))
    return Z3RuleSet(
        rules=tuple(
            Z3OwnerRule(
                rule_id=rule.rule_id,
                owner_class=rule.owner_class,
                status=rule.status,
                decision_label=rule.decision_label,
                priority=rule.priority,
                all_of=tuple(
                    MetricPredicate(
                        metric_id=predicate.metric_id,
                        operator=predicate.operator,
                        threshold=predicate.threshold,
                    )
                    for predicate in rule.all_of
                ),
                any_of=tuple(
                    MetricPredicate(
                        metric_id=predicate.metric_id,
                        operator=predicate.operator,
                        threshold=predicate.threshold,
                    )
                    for predicate in rule.any_of
                ),
                none_of=tuple(
                    MetricPredicate(
                        metric_id=predicate.metric_id,
                        operator=predicate.operator,
                        threshold=predicate.threshold,
                    )
                    for predicate in rule.none_of
                ),
                location_metric_id=rule.location_metric_id,
            )
            for rule in canonical.rules
        ),
        pass_status=canonical.pass_status,
        rz_specific_status="REQUIRES_SPATIAL_COMPONENT_AGREEMENT",
    )


__all__ = ["build_constant_state_registry", "build_constant_state_ruleset"]
