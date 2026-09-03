"""Typed models for registry- and Z3-driven diagnosis."""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EvidenceTolerances(BaseModel):
    """Validated absolute tolerances for the built-in constant-state preset."""

    model_config = ConfigDict(frozen=True)

    face_value_abs: float = Field(default=1.0e-14, ge=0.0)
    surface_vector_abs: float = Field(default=1.0e-14, ge=0.0)
    surface_closure_abs: float = Field(default=1.0e-14, ge=0.0)
    gradient_match_abs: float = Field(default=1.0e-12, ge=0.0)
    qpx_gradient_abs: float = Field(default=1.0e-12, ge=0.0)


class FailureLocation(BaseModel):
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
    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(min_length=1)
    metric_id: str = Field(min_length=1)
    threshold: float = Field(ge=0.0)
    owner_class: str = Field(min_length=1)
    status: str = Field(min_length=1)
    decision_label: str = Field(min_length=1)
    priority: int = Field(ge=0)


class DiagnosisRuleRegistry(BaseModel):
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
        merged_metrics = dict(self.metrics)
        merged_metrics.update(dict(metrics or {}))
        return DiagnosisRuleRegistry(
            metrics=merged_metrics,
            rules=(*self.rules, *tuple(rules)),
            pass_status=self.pass_status,
            rz_specific_status=self.rz_specific_status,
        )


class MetricPredicate(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric_id: str = Field(min_length=1)
    operator: Literal["gt", "ge", "lt", "le", "eq", "ne"] = "gt"
    threshold: float

    @field_validator("threshold")
    @classmethod
    def _finite_threshold(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Z3 predicate threshold must be finite")
        return value


class Z3OwnerRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(min_length=1)
    owner_class: str = Field(min_length=1)
    status: str = Field(min_length=1)
    decision_label: str = Field(min_length=1)
    priority: int = Field(ge=0)
    all_of: tuple[MetricPredicate, ...] = ()
    any_of: tuple[MetricPredicate, ...] = ()
    none_of: tuple[MetricPredicate, ...] = ()
    location_metric_id: str | None = None

    @model_validator(mode="after")
    def _nonempty_logic(self) -> "Z3OwnerRule":
        if not (self.all_of or self.any_of or self.none_of):
            raise ValueError("Z3 owner rule must declare at least one predicate")
        return self

    @property
    def metric_ids(self) -> set[str]:
        return {
            predicate.metric_id
            for predicate in (*self.all_of, *self.any_of, *self.none_of)
        }


class Z3RuleSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    rules: tuple[Z3OwnerRule, ...]
    pass_status: str = "CONSTANT_STATE_PASS"
    rz_specific_status: str = "REQUIRES_SPATIAL_COMPONENT_AGREEMENT"

    @model_validator(mode="after")
    def _validate_rules(self) -> "Z3RuleSet":
        ids: set[str] = set()
        priorities: dict[int, str] = {}
        for rule in self.rules:
            if rule.rule_id in ids:
                raise ValueError(f"duplicate Z3 rule_id: {rule.rule_id!r}")
            ids.add(rule.rule_id)
            prior = priorities.get(rule.priority)
            if prior is not None:
                raise ValueError(
                    f"Z3 priority {rule.priority} is shared by rules "
                    f"{prior!r} and {rule.rule_id!r}"
                )
            priorities[rule.priority] = rule.rule_id
            if rule.location_metric_id is not None and rule.location_metric_id not in rule.metric_ids:
                raise ValueError(
                    f"Z3 rule {rule.rule_id!r} location_metric_id "
                    f"{rule.location_metric_id!r} is not referenced by the rule"
                )
        return self

    @property
    def ordered_rules(self) -> tuple[Z3OwnerRule, ...]:
        return tuple(sorted(self.rules, key=lambda rule: rule.priority))

    @property
    def required_metric_ids(self) -> set[str]:
        required: set[str] = set()
        for rule in self.rules:
            required.update(rule.metric_ids)
        return required

    def extend(self, rules: Iterable[Z3OwnerRule]) -> "Z3RuleSet":
        return Z3RuleSet(
            rules=(*self.rules, *tuple(rules)),
            pass_status=self.pass_status,
            rz_specific_status=self.rz_specific_status,
        )


class Z3Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    solver_status: Literal["SATISFIED", "UNSATISFIABLE", "UNKNOWN"]
    primary_owner_class: str | None = None
    selected_rule_id: str | None = None
    status: str
    z3_model: str | None = None


class DiagnosisReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    primary_owner_class: str | None = None
    selected_rule_id: str | None = None
    metrics: dict[str, float]
    failing_locations: list[FailureLocation] = Field(default_factory=list)
    rz_specific_status: str = "REQUIRES_SPATIAL_COMPONENT_AGREEMENT"
    decision_order: list[str] = Field(default_factory=list)
    solver_status: str | None = None
    z3_model: str | None = None


__all__ = [
    "DiagnosticMetricSpec",
    "DiagnosisReport",
    "DiagnosisRule",
    "DiagnosisRuleRegistry",
    "EvidenceTolerances",
    "FailureLocation",
    "MetricPredicate",
    "Z3Decision",
    "Z3OwnerRule",
    "Z3RuleSet",
]
