"""Jacobian correctness reasoning over parsed comparison evidence."""
from __future__ import annotations

import math
from typing import Any, Mapping

from .engines.z3 import evaluate_rules
from .rules import MetricPredicate, ReasoningRule, RuleSet


def build_jacobian_ruleset(relative_tolerance: float) -> RuleSet:
    if relative_tolerance < 0:
        raise ValueError("relative_tolerance must be non-negative")
    return RuleSet(
        rules=(
            ReasoningRule(
                rule_id="jacobian_mismatch",
                owner_class="JACOBIAN_MISMATCH",
                status="HOLD",
                decision_label="Jacobian mismatch",
                priority=10,
                any_of=(
                    MetricPredicate("nonfinite_count", "gt", 0.0),
                    MetricPredicate(
                        "worst_relative_frobenius_error",
                        "gt",
                        float(relative_tolerance),
                    ),
                ),
            ),
        ),
        pass_status="PASS",
    )


def diagnose_jacobian_evidence(
    evidence: Mapping[str, Any], *, relative_tolerance: float
) -> dict[str, Any]:
    count = int(evidence.get("comparison_count", 0))
    tests = list(evidence.get("tests", []))
    if count == 0:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_EVIDENCE_INSUFFICIENT",
            "reason": "PETSc -snes_test_jacobian produced no parseable Jacobian comparison",
            "relative_tolerance": relative_tolerance,
            "tests": tests,
        }

    nonfinite = list(evidence.get("nonfinite", []))
    nonfinite_count = int(evidence.get("nonfinite_count", len(nonfinite)))
    worst_raw = evidence.get("worst_relative_frobenius_error")
    worst = float(worst_raw) if worst_raw is not None else math.inf
    z3_worst = worst if math.isfinite(worst) else 0.0
    decision = evaluate_rules(
        {
            "nonfinite_count": float(nonfinite_count),
            "worst_relative_frobenius_error": z3_worst,
        },
        build_jacobian_ruleset(relative_tolerance),
    )

    if decision.primary_owner_class == "JACOBIAN_MISMATCH":
        return {
            "status": "HOLD",
            "class": "JACOBIAN_MISMATCH",
            "reason": (
                "assembled-vs-finite-difference Jacobian relative Frobenius error exceeds "
                f"the declared tolerance {relative_tolerance:g} or is non-finite"
            ),
            "relative_tolerance": relative_tolerance,
            "worst_relative_frobenius_error": worst,
            "nonfinite": nonfinite,
            "tests": tests,
        }
    return {
        "status": "PASS",
        "class": "JACOBIAN_CORRECTNESS_PASS",
        "reason": "all observed PETSc Jacobian comparisons satisfy the declared relative tolerance",
        "relative_tolerance": relative_tolerance,
        "worst_relative_frobenius_error": worst,
        "nonfinite": [],
        "tests": tests,
    }


__all__ = ["build_jacobian_ruleset", "diagnose_jacobian_evidence"]
