"""Backend-neutral diagnosis orchestration over quantitative analysis outputs."""
from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from qpx_harness.analysis.diagnostic_metrics import (
    DiagnosticMetricSpec,
    aggregate_metric_values,
    failure_location_rows,
)

from .diagnosis import DiagnosisReport, FailureLocation
from .engines.z3 import evaluate_rules
from .rules import RuleSet


def evaluate_diagnostic_rules(
    frames: Mapping[str, pl.DataFrame],
    metrics: Mapping[str, DiagnosticMetricSpec],
    ruleset: RuleSet,
    *,
    top_k_failures: int = 5,
) -> DiagnosisReport:
    """Evaluate backend-neutral rules over deterministic diagnostic metrics.

    Quantitative aggregation and spatial row extraction remain owned by Analysis;
    this function owns only reasoning orchestration and diagnosis representation.
    """
    if top_k_failures <= 0:
        raise ValueError("top_k_failures must be positive")

    report_metrics, metric_values, frames_by_metric = aggregate_metric_values(
        frames,
        metrics,
    )
    unknown_metrics = sorted(ruleset.required_metric_ids.difference(metrics))
    if unknown_metrics:
        raise ValueError(
            "reasoning rule set references metrics not registered for aggregation: "
            + ", ".join(unknown_metrics)
        )

    decision = evaluate_rules(metric_values, ruleset)
    failures: list[FailureLocation] = []
    if decision.selected_rule_id is not None:
        selected_rule = next(
            rule for rule in ruleset.rules if rule.rule_id == decision.selected_rule_id
        )
        location_metric_id = selected_rule.location_metric_id
        if location_metric_id is not None:
            metric = metrics[location_metric_id]
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
                    f"reasoning rule {selected_rule.rule_id!r} needs exactly one predicate "
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
        metrics=tuple(report_metrics.items()),
        primary_owner_class=decision.primary_owner_class,
        selected_rule_id=decision.selected_rule_id,
        failing_locations=tuple(failures),
        decision_order=tuple(rule.decision_label for rule in ruleset.ordered_rules),
        solver_status=decision.solver_status,
        backend_model=decision.backend_model,
    )


__all__ = ["evaluate_diagnostic_rules"]
