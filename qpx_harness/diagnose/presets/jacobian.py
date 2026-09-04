"""Compatibility facade for canonical Jacobian correctness validation."""
from __future__ import annotations

from typing import Any, Mapping

from qpx_harness.validation.jacobian import (
    build_jacobian_ruleset as _build_canonical_ruleset,
    diagnose_jacobian_evidence,
)

from ..models import MetricPredicate, Z3OwnerRule, Z3RuleSet


def build_jacobian_ruleset(relative_tolerance: float) -> Z3RuleSet:
    """Project canonical validation rules into the historical Z3 DTO shape."""
    canonical = _build_canonical_ruleset(relative_tolerance)
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
        rz_specific_status="NOT_APPLICABLE",
    )


__all__ = ["build_jacobian_ruleset", "diagnose_jacobian_evidence"]
