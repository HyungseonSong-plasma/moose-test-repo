"""Compatibility facade for canonical coupled-solver reasoning."""
from __future__ import annotations

from typing import Any, Mapping

from qpx_harness.reasoning.coupled_solver import (
    build_coupled_solver_ruleset as _build_canonical_ruleset,
    coupled_solver_metric_values,
    diagnose_coupled_runtime_evidence,
)

from ..models import MetricPredicate, Z3OwnerRule, Z3RuleSet


def build_coupled_solver_ruleset() -> Z3RuleSet:
    """Project the canonical backend-neutral rules into the legacy DTO shape."""
    canonical = _build_canonical_ruleset()
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


__all__ = [
    "build_coupled_solver_ruleset",
    "coupled_solver_metric_values",
    "diagnose_coupled_runtime_evidence",
]
