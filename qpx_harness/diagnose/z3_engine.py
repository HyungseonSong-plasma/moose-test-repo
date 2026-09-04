"""Deprecated compatibility facade for canonical Z3 reasoning mechanics.

Canonical backend owner: :mod:`qpx_harness.reasoning.engines.z3`.
This module preserves the legacy Pydantic-facing API while callers migrate.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

from qpx_harness.reasoning.engines.z3 import evaluate_rules
from qpx_harness.reasoning.rules import (
    MetricPredicate as ReasoningMetricPredicate,
    ReasoningRule,
    RuleSet,
)

from .models import (
    DiagnosisRuleRegistry,
    MetricPredicate,
    Z3Decision,
    Z3OwnerRule,
    Z3RuleSet,
)


def ruleset_from_registry(registry: DiagnosisRuleRegistry) -> Z3RuleSet:
    """Preserve the legacy registry-to-ruleset projection during migration."""
    return Z3RuleSet(
        rules=tuple(
            Z3OwnerRule(
                rule_id=rule.rule_id,
                owner_class=rule.owner_class,
                status=rule.status,
                decision_label=rule.decision_label,
                priority=rule.priority,
                all_of=(
                    MetricPredicate(
                        metric_id=rule.metric_id,
                        operator="gt",
                        threshold=rule.threshold,
                    ),
                ),
                location_metric_id=rule.metric_id,
            )
            for rule in registry.rules
        ),
        pass_status=registry.pass_status,
        rz_specific_status=registry.rz_specific_status,
    )


def _canonical_predicate(predicate: MetricPredicate) -> ReasoningMetricPredicate:
    return ReasoningMetricPredicate(
        metric_id=predicate.metric_id,
        operator=predicate.operator,
        threshold=predicate.threshold,
    )


def _canonical_rule(rule: Z3OwnerRule) -> ReasoningRule:
    return ReasoningRule(
        rule_id=rule.rule_id,
        owner_class=rule.owner_class,
        status=rule.status,
        decision_label=rule.decision_label,
        priority=rule.priority,
        all_of=tuple(_canonical_predicate(p) for p in rule.all_of),
        any_of=tuple(_canonical_predicate(p) for p in rule.any_of),
        none_of=tuple(_canonical_predicate(p) for p in rule.none_of),
        location_metric_id=rule.location_metric_id,
    )


def _canonical_ruleset(ruleset: Z3RuleSet) -> RuleSet:
    return RuleSet(
        rules=tuple(_canonical_rule(rule) for rule in ruleset.rules),
        pass_status=ruleset.pass_status,
    )


class Z3DiagnosisEngine:
    """Compatibility wrapper around the canonical reasoning Z3 backend."""

    def __init__(self, ruleset: Z3RuleSet):
        self.ruleset = ruleset

    def diagnose(self, metric_values: Mapping[str, float]) -> Z3Decision:
        missing = sorted(self.ruleset.required_metric_ids.difference(metric_values))
        if missing:
            raise ValueError(
                "Z3 diagnosis missing required metric values: " + ", ".join(missing)
            )

        values: dict[str, float] = {}
        for metric_id in self.ruleset.required_metric_ids:
            value = float(metric_values[metric_id])
            if not math.isfinite(value):
                raise ValueError(f"Z3 diagnosis metric {metric_id!r} is non-finite")
            values[metric_id] = value

        decision = evaluate_rules(values, _canonical_ruleset(self.ruleset))
        return Z3Decision(
            solver_status=decision.solver_status,
            primary_owner_class=decision.primary_owner_class,
            selected_rule_id=decision.selected_rule_id,
            status=decision.status,
            z3_model=decision.backend_model,
        )


__all__ = ["Z3DiagnosisEngine", "ruleset_from_registry"]
