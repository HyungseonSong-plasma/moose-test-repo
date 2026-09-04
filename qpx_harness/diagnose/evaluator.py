"""Compatibility diagnosis orchestration over canonical analysis and reasoning owners."""
from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from qpx_harness.analysis.diagnostic_metrics import (
    aggregate_metric_values,
    failure_location_rows,
)

from .models import (
    DiagnosisReport,
    DiagnosisRuleRegistry,
    FailureLocation,
    Z3RuleSet,
)
from .z3_engine import Z3DiagnosisEngine, ruleset_from_registry


def evaluate_diagnosis_registry(
    frames: Mapping[str, pl.DataFrame],
    registry: DiagnosisRuleRegistry,
    *,
    top_k_failures: int = 5,
    z3_ruleset: Z3RuleSet | None = None,
) -> DiagnosisReport:
    """Aggregate canonical analysis metrics, then delegate owner selection to Z3."""
    if top_k_failures <= 0:
        raise ValueError("top_k_failures must be positive")

    report_metrics, metric_values, frames_by_metric = aggregate_metric_values(
        frames,
        registry.metrics,
    )

    active_ruleset = z3_ruleset or ruleset_from_registry(registry)
    unknown_metrics = sorted(active_ruleset.required_metric_ids.difference(registry.metrics))
    if unknown_metrics:
        raise ValueError(
            "Z3 rule set references metrics not registered for aggregation: "
            + ", ".join(unknown_metrics)
        )

    decision = Z3DiagnosisEngine(active_ruleset).diagnose(metric_values)
    failures: list[FailureLocation] = []
    if decision.selected_rule_id is not None:
        selected_rule = next(
            rule
            for rule in active_ruleset.rules
            if rule.rule_id == decision.selected_rule_id
        )
        location_metric_id = selected_rule.location_metric_id
        if location_metric_id is not None:
            metric = registry.metrics[location_metric_id]
            predicates = [
                predicate
                for predicate in (
                    *selected_rule.all_of,
                    *selected_rule.any_of,
                    *selected_rule.none_of,
                )
                if predicate.metric_id == location_metric_id
            ]
            if len(predicates) != 1:
                raise ValueError(
                    f"Z3 rule {selected_rule.rule_id!r} needs exactly one predicate "
                    f"for location metric {location_metric_id!r}"
                )
            predicate = predicates[0]
            if predicate.operator not in {"gt", "ge"}:
                raise ValueError(
                    "failure localization currently requires a gt/ge threshold predicate"
                )
            failures = [
                FailureLocation(**row)
                for row in failure_location_rows(
                    frames_by_metric[location_metric_id],
                    metric,
                    predicate.threshold,
                    inclusive=predicate.operator == "ge",
                    top_k=top_k_failures,
                )
            ]

    return DiagnosisReport(
        status=decision.status,
        primary_owner_class=decision.primary_owner_class,
        selected_rule_id=decision.selected_rule_id,
        metrics=report_metrics,
        failing_locations=failures,
        rz_specific_status=active_ruleset.rz_specific_status,
        decision_order=[rule.decision_label for rule in active_ruleset.ordered_rules],
        solver_status=decision.solver_status,
        z3_model=decision.z3_model,
    )


__all__ = ["evaluate_diagnosis_registry"]
