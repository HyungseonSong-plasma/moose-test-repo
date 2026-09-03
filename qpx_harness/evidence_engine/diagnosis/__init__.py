"""Public diagnosis API: models, evaluator, presets, and Z3 rule injection."""
from __future__ import annotations

from typing import Any

import polars as pl

from .evaluator import evaluate_diagnosis_registry
from .models import (
    DiagnosticMetricSpec,
    DiagnosisReport,
    DiagnosisRule,
    DiagnosisRuleRegistry,
    EvidenceTolerances,
    FailureLocation,
    MetricPredicate,
    Z3Decision,
    Z3OwnerRule,
    Z3RuleSet,
)
from .presets import build_constant_state_registry, build_constant_state_ruleset
from .z3_engine import Z3DiagnosisEngine, ruleset_from_registry


def summarize_constant_state_report(
    face: pl.DataFrame,
    cell: pl.DataFrame,
    *,
    tolerances: EvidenceTolerances | None = None,
    top_k_failures: int = 5,
    registry: DiagnosisRuleRegistry | None = None,
    z3_ruleset: Z3RuleSet | None = None,
) -> DiagnosisReport:
    """Return a typed Green-Gauss report with an injectable Z3 policy set."""
    active_registry = registry or build_constant_state_registry(tolerances)
    active_ruleset = z3_ruleset
    if active_ruleset is None and registry is None:
        active_ruleset = build_constant_state_ruleset(tolerances)
    return evaluate_diagnosis_registry(
        {"face": face, "cell": cell},
        active_registry,
        top_k_failures=top_k_failures,
        z3_ruleset=active_ruleset,
    )


def summarize_constant_state(
    face: pl.DataFrame,
    cell: pl.DataFrame,
    *,
    tolerances: EvidenceTolerances | None = None,
    top_k_failures: int = 5,
    registry: DiagnosisRuleRegistry | None = None,
    z3_ruleset: Z3RuleSet | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper returning the validated report as a dictionary."""
    return summarize_constant_state_report(
        face,
        cell,
        tolerances=tolerances,
        top_k_failures=top_k_failures,
        registry=registry,
        z3_ruleset=z3_ruleset,
    ).model_dump(mode="python")


__all__ = [
    "DiagnosticMetricSpec",
    "DiagnosisReport",
    "DiagnosisRule",
    "DiagnosisRuleRegistry",
    "EvidenceTolerances",
    "FailureLocation",
    "MetricPredicate",
    "Z3Decision",
    "Z3DiagnosisEngine",
    "Z3OwnerRule",
    "Z3RuleSet",
    "build_constant_state_registry",
    "build_constant_state_ruleset",
    "evaluate_diagnosis_registry",
    "ruleset_from_registry",
    "summarize_constant_state",
    "summarize_constant_state_report",
]
