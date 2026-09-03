"""Polars metric aggregation and Z3-backed diagnosis evaluation."""
from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from .models import (
    DiagnosticMetricSpec,
    DiagnosisReport,
    DiagnosisRuleRegistry,
    FailureLocation,
    Z3RuleSet,
)
from .z3_engine import Z3DiagnosisEngine, ruleset_from_registry


def _frame_for_metric(
    frames: Mapping[str, pl.DataFrame], metric: DiagnosticMetricSpec
) -> pl.DataFrame:
    frame = frames.get(metric.source)
    if frame is None:
        raise ValueError(
            f"diagnosis metric {metric.metric_id!r} requires missing source frame "
            f"{metric.source!r}"
        )
    if frame.height == 0:
        raise ValueError(
            f"diagnosis metric {metric.metric_id!r} received no rows from "
            f"source {metric.source!r}"
        )
    if metric.column not in frame.columns:
        raise ValueError(
            f"diagnosis metric {metric.metric_id!r} missing required column: {metric.column}"
        )
    return frame


def _metric_max_abs(frame: pl.DataFrame, metric: DiagnosticMetricSpec) -> float:
    invalid_count = frame.select(
        pl.col(metric.column).is_finite().fill_null(False).not_().sum()
    ).item()
    if int(invalid_count or 0) != 0:
        raise ValueError(
            f"diagnosis metric {metric.metric_id!r} column {metric.column!r} "
            "contains non-finite values"
        )
    value = frame.select(pl.col(metric.column).abs().max()).item()
    return float(value if value is not None else 0.0)


def _failure_locations(
    frame: pl.DataFrame,
    metric: DiagnosticMetricSpec,
    threshold: float,
    *,
    inclusive: bool,
    top_k: int,
) -> list[FailureLocation]:
    if metric.entity_kind is None:
        return []
    if top_k <= 0:
        raise ValueError("top_k_failures must be positive")

    required = {"elem_id", metric.x_col, metric.y_col}
    if metric.entity_kind == "face":
        required.add("face_id")
    missing = sorted(str(name) for name in required if name not in frame.columns)
    if missing:
        raise ValueError(
            f"{metric.entity_kind} diagnosis missing location columns for "
            f"{metric.metric_id}: {', '.join(missing)}"
        )

    absolute_error = pl.col(metric.column).abs()
    predicate = absolute_error >= threshold if inclusive else absolute_error > threshold
    failed = (
        frame.with_columns(absolute_error.alias("__abs_error"))
        .filter(predicate)
        .sort("__abs_error", descending=True)
        .head(top_k)
    )

    locations: list[FailureLocation] = []
    for row in failed.iter_rows(named=True):
        locations.append(
            FailureLocation(
                entity_kind=metric.entity_kind,
                metric=metric.column,
                elem_id=int(row["elem_id"]),
                face_id=(
                    int(row["face_id"]) if metric.entity_kind == "face" else None
                ),
                centroid=(float(row[metric.x_col]), float(row[metric.y_col])),
                error_value=float(row["__abs_error"]),
                run_id=(str(row["run_id"]) if row.get("run_id") is not None else None),
                case_id=(str(row["case_id"]) if row.get("case_id") is not None else None),
            )
        )
    return locations


def evaluate_diagnosis_registry(
    frames: Mapping[str, pl.DataFrame],
    registry: DiagnosisRuleRegistry,
    *,
    top_k_failures: int = 5,
    z3_ruleset: Z3RuleSet | None = None,
) -> DiagnosisReport:
    """Aggregate numerical metrics, then delegate owner selection to Z3.

    ``z3_ruleset`` is fully injectable. When omitted, the legacy registry rules
    are losslessly adapted into one-predicate Z3 rules, preserving existing APIs
    while making SMT logic the canonical decision path.
    """
    if top_k_failures <= 0:
        raise ValueError("top_k_failures must be positive")

    report_metrics: dict[str, float] = {}
    metric_values: dict[str, float] = {}
    frames_by_metric: dict[str, pl.DataFrame] = {}
    for metric_id, metric in registry.metrics.items():
        frame = _frame_for_metric(frames, metric)
        frames_by_metric[metric_id] = frame
        value = _metric_max_abs(frame, metric)
        metric_values[metric_id] = value
        report_metrics[metric.report_key] = value

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
            failures = _failure_locations(
                frames_by_metric[location_metric_id],
                metric,
                predicate.threshold,
                inclusive=predicate.operator == "ge",
                top_k=top_k_failures,
            )

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
