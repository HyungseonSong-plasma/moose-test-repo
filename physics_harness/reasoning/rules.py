"""Backend-neutral reasoning rule representation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MetricPredicate:
    metric_id: str
    operator: Literal["gt", "ge", "lt", "le", "eq", "ne"] = "gt"
    threshold: float = 0.0


@dataclass(frozen=True)
class ReasoningRule:
    rule_id: str
    owner_class: str
    status: str
    decision_label: str
    priority: int
    all_of: tuple[MetricPredicate, ...] = ()
    any_of: tuple[MetricPredicate, ...] = ()
    none_of: tuple[MetricPredicate, ...] = ()
    location_metric_id: str | None = None

    def __post_init__(self) -> None:
        if not (self.all_of or self.any_of or self.none_of):
            raise ValueError("reasoning rule must declare at least one predicate")

    @property
    def metric_ids(self) -> set[str]:
        return {p.metric_id for p in (*self.all_of, *self.any_of, *self.none_of)}


@dataclass(frozen=True)
class RuleSet:
    rules: tuple[ReasoningRule, ...]
    pass_status: str = "PASS"

    @property
    def ordered_rules(self) -> tuple[ReasoningRule, ...]:
        return tuple(sorted(self.rules, key=lambda rule: rule.priority))

    @property
    def required_metric_ids(self) -> set[str]:
        result: set[str] = set()
        for rule in self.rules:
            result.update(rule.metric_ids)
        return result


__all__ = ["MetricPredicate", "ReasoningRule", "RuleSet"]
