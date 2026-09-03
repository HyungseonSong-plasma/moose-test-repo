"""Registry-driven diagnosis for numerical evidence.

The generic evaluator is intentionally independent of Green-Gauss. A registry
binds metric columns to source frames and ordered decision rules. The existing
constant-state API is retained as a compatibility layer that builds the canonical
Green-Gauss registry from ``EvidenceTolerances``.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceTolerances(BaseModel):
    """Validated absolute tolerances for the built-in constant-state registry."""

    model_config = ConfigDict(frozen=True)

    face_value_abs: float = Field(default=1.0e-14, ge=0.0)
    surface_vector_abs: float = Field(default=1.0e-14, ge=0.0)
    surface_closure_abs: float = Field(default=1.0e-14, ge=0.0)
    gradient_match_abs: float = Field(default=1.0e-12, ge=0.0)
    # Historical public name retained for compatibility. The registered metric
    # itself is solver-agnostic ``runtime_gradient``.
    qpx_gradient_abs: float = Field(default=1.0e-12, ge=0.0)


class FailureLocation(BaseModel):
    """Top-ranked spatial location contributing to the selected diagnosis rule."""

    model_config = ConfigDict(frozen=True)

    entity_kind: Literal["face", "cell"]
    metric: str
    elem_id: int
    face_id: int | None = None
    centroid: tuple[float, float]
    error_value: float = Field(ge=0.0)
    run_id: str | None = None
    case_id: str | None = None


class DiagnosticMetricSpec(BaseModel):
    """One scalar evidence metric available to diagnosis rules.

    Metrics are aggregated as an absolute maximum. New diagnostics should place
    any required derived error quantity in the source frame first, then register
    that column here. ``entity_kind=None`` supports run-level metrics for which a
    spatial failure location is not meaningful.
    """

    model_config = ConfigDict(frozen=True)

    metric_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    column: str = Field(min_length=1)
    report_key: str = Field(min_length=1)
    entity_kind: Literal["face", "cell"] | None = None
    x_col: str | None = None
    y_col: str | None = None

    @model_validator(mode="after")
    def _validate_location_columns(self) -> "DiagnosticMetricSpec":
        if self.entity_kind is None:
            if self.x_col is not None or self.y_col is not None:
                raise ValueError("non-spatial metrics may not declare centroid columns")
            return self
        if self.x_col is None or self.y_col is None:
            raise ValueError("spatial metrics require both x_col and y_col")
        return self


class DiagnosisRule(BaseModel):
    """Ordered owner-class decision attached to one registered metric."""

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(min_length=1)
    metric_id: str = Field(min_length=1)
    threshold: float = Field(ge=0.0)
    owner_class: str = Field(min_length=1)
    status: str = Field(min_length=1)
    decision_label: str = Field(min_length=1)
    priority: int = Field(ge=0)


class DiagnosisRuleRegistry(BaseModel):
    """Validated metric registry plus deterministic first-match decision rules."""

    model_config = ConfigDict(frozen=True)

    metrics: dict[str, DiagnosticMetricSpec]
    rules: tuple[DiagnosisRule, ...] = ()
    pass_status: str = "CONSTANT_STATE_PASS"
    rz_specific_status: str = "REQUIRES_SPATIAL_COMPONENT_AGREEMENT"

    @model_validator(mode="after")
    def _validate_registry(self) -> "DiagnosisRuleRegistry":
        report_keys: dict[str, str] = {}
        for key, metric in self.metrics.items():
            if key != metric.metric_id:
                raise ValueError(
                    f"metric registry key {key!r} must equal metric_id {metric.metric_id!r}"
                )
            previous = report_keys.get(metric.report_key)
            if previous is not None:
                raise ValueError(
                    f"report key {metric.report_key!r} is shared by metrics "
                    f"{previous!r} and {key!r}"
                )
            report_keys[metric.report_key] = key

        rule_ids: set[str] = set()
        priorities: dict[int, str] = {}
        for rule in self.rules:
            if rule.rule_id in rule_ids:
                raise ValueError(f"duplicate diagnosis rule_id: {rule.rule_id!r}")
            rule_ids.add(rule.rule_id)
            if rule.metric_id not in self.metrics:
                raise ValueError(
                    f"diagnosis rule {rule.rule_id!r} references unknown metric "
                    f"{rule.metric_id!r}"
                )
            previous_rule = priorities.get(rule.priority)
            if previous_rule is not None:
                raise ValueError(
                    f"diagnosis priority {rule.priority} is shared by rules "
                    f"{previous_rule!r} and {rule.rule_id!r}"
                )
            priorities[rule.priority] = rule.rule_id
        return self

    @property
    def ordered_rules(self) -> tuple[DiagnosisRule, ...]:
        return tuple(sorted(self.rules, key=lambda rule: rule.priority))

    def extend(
        self,
        *,
        metrics: Mapping[str, DiagnosticMetricSpec] | None = None,
        rules: Iterable[DiagnosisRule] = (),
    ) -> "DiagnosisRuleRegistry":
        """Return a validated registry containing additional metrics/rules."""
        merged_metrics = dict(self.metrics)
        merged_metrics.update(dict(metrics or {}))
        return DiagnosisRuleRegistry(
            metrics=merged_metrics,
            rules=(*self.rules, *tuple(rules)),
            pass_status=self.pass_status,
            rz_specific_status=self.rz_specific_status,
        )


class DiagnosisReport(BaseModel):
    """Validated machine-readable result from one registry evaluation."""

    model_config = ConfigDict(frozen=True)

    status: str
    primary_owner_class: str | None = None
    selected_rule_id: str | None = None
    metrics: dict[str, float]
    failing_locations: list[FailureLocation] = Field(default_factory=list)
    rz_specific_status: str = "REQUIRES_SPATIAL_COMPONENT_AGREEMENT"
    decision_order: list[str] = Field(default_factory=list)


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

    failed = (
        frame.with_columns(pl.col(metric.column).abs().alias("__abs_error"))
        .filter(pl.col("__abs_error") > threshold)
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
) -> DiagnosisReport:
    """Evaluate all registered metrics and apply the first triggered ordered rule."""
    if top_k_failures <= 0:
        raise ValueError("top_k_failures must be positive")

    metric_values: dict[str, float] = {}
    frames_by_metric: dict[str, pl.DataFrame] = {}
    for metric_id, metric in registry.metrics.items():
        frame = _frame_for_metric(frames, metric)
        frames_by_metric[metric_id] = frame
        metric_values[metric.report_key] = _metric_max_abs(frame, metric)

    selected: DiagnosisRule | None = None
    failures: list[FailureLocation] = []
    for rule in registry.ordered_rules:
        metric = registry.metrics[rule.metric_id]
        value = metric_values[metric.report_key]
        if value <= rule.threshold:
            continue
        selected = rule
        failures = _failure_locations(
            frames_by_metric[rule.metric_id],
            metric,
            rule.threshold,
            top_k=top_k_failures,
        )
        break

    return DiagnosisReport(
        status=(selected.status if selected else registry.pass_status),
        primary_owner_class=(selected.owner_class if selected else None),
        selected_rule_id=(selected.rule_id if selected else None),
        metrics=metric_values,
        failing_locations=failures,
        rz_specific_status=registry.rz_specific_status,
        decision_order=[rule.decision_label for rule in registry.ordered_rules],
    )


def build_constant_state_registry(
    tolerances: EvidenceTolerances | None = None,
) -> DiagnosisRuleRegistry:
    """Build the canonical Green-Gauss constant-state registry."""
    tol = tolerances or EvidenceTolerances()
    metrics = {
        "face_value_delta": DiagnosticMetricSpec(
            metric_id="face_value_delta",
            source="face",
            column="field_face_delta",
            report_key="max_abs_field_face_delta",
            entity_kind="face",
            x_col="face_x",
            y_col="face_y",
        ),
        "surface_vector_delta": DiagnosticMetricSpec(
            metric_id="surface_vector_delta",
            source="face",
            column="surface_delta_norm",
            report_key="max_surface_delta_norm",
            entity_kind="face",
            x_col="face_x",
            y_col="face_y",
        ),
        "surface_closure": DiagnosticMetricSpec(
            metric_id="surface_closure",
            source="cell",
            column="surface_closure_norm",
            report_key="max_surface_closure_norm",
            entity_kind="cell",
            x_col="cell_x",
            y_col="cell_y",
        ),
        "gradient_reconstruction_delta": DiagnosticMetricSpec(
            metric_id="gradient_reconstruction_delta",
            source="cell",
            column="gradient_delta_norm",
            report_key="max_gradient_delta_norm",
            entity_kind="cell",
            x_col="cell_x",
            y_col="cell_y",
        ),
        "runtime_gradient": DiagnosticMetricSpec(
            metric_id="runtime_gradient",
            source="cell",
            column="runtime_grad_norm",
            report_key="max_runtime_grad_norm",
            entity_kind="cell",
            x_col="cell_x",
            y_col="cell_y",
        ),
        "reconstructed_gradient": DiagnosticMetricSpec(
            metric_id="reconstructed_gradient",
            source="cell",
            column="reconstructed_grad_norm",
            report_key="max_reconstructed_grad_norm",
        ),
    }
    rules = (
        DiagnosisRule(
            rule_id="face_value_reconstruction",
            metric_id="face_value_delta",
            threshold=tol.face_value_abs,
            owner_class="FACE_VALUE_RECONSTRUCTION",
            status="ISOLATED_OWNER_CLASS",
            decision_label="face value reconstruction",
            priority=10,
        ),
        DiagnosisRule(
            rule_id="surface_vector_construction",
            metric_id="surface_vector_delta",
            threshold=tol.surface_vector_abs,
            owner_class="SURFACE_VECTOR_CONSTRUCTION",
            status="ISOLATED_OWNER_CLASS",
            decision_label="surface vector construction",
            priority=20,
        ),
        DiagnosisRule(
            rule_id="rz_surface_geometry_closure",
            metric_id="surface_closure",
            threshold=tol.surface_closure_abs,
            owner_class="RZ_SURFACE_GEOMETRY_CLOSURE",
            status="FAVORED",
            decision_label="RZ surface/volume closure",
            priority=30,
        ),
        DiagnosisRule(
            rule_id="missing_runtime_arithmetic_path",
            metric_id="gradient_reconstruction_delta",
            threshold=tol.gradient_match_abs,
            owner_class="MISSING_MOOSE_ARITHMETIC_PATH",
            status="UNRESOLVED",
            decision_label="runtime-vs-reconstruction arithmetic path",
            priority=40,
        ),
        DiagnosisRule(
            rule_id="green_gauss_constant_preservation",
            metric_id="runtime_gradient",
            threshold=tol.qpx_gradient_abs,
            owner_class="FV_GREEN_GAUSS_CELL_GRADIENT_CONSTANT_PRESERVATION",
            status="ISOLATED_OWNER_CLASS",
            decision_label="Green-Gauss constant preservation",
            priority=50,
        ),
    )
    return DiagnosisRuleRegistry(metrics=metrics, rules=rules)


def summarize_constant_state_report(
    face: pl.DataFrame,
    cell: pl.DataFrame,
    *,
    tolerances: EvidenceTolerances | None = None,
    top_k_failures: int = 5,
    registry: DiagnosisRuleRegistry | None = None,
) -> DiagnosisReport:
    """Return a typed constant-state report using the registry-driven evaluator.

    A caller may provide an extended registry to add new metrics/rules without
    changing this function. When omitted, the canonical Green-Gauss registry is
    built from ``tolerances``.
    """
    active_registry = registry or build_constant_state_registry(tolerances)
    return evaluate_diagnosis_registry(
        {"face": face, "cell": cell},
        active_registry,
        top_k_failures=top_k_failures,
    )


def summarize_constant_state(
    face: pl.DataFrame,
    cell: pl.DataFrame,
    *,
    tolerances: EvidenceTolerances | None = None,
    top_k_failures: int = 5,
    registry: DiagnosisRuleRegistry | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper returning the validated report as a dictionary."""
    return summarize_constant_state_report(
        face,
        cell,
        tolerances=tolerances,
        top_k_failures=top_k_failures,
        registry=registry,
    ).model_dump(mode="python")
