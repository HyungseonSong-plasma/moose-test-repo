"""Coupled nonlinear-solver diagnosis over canonical runtime evidence."""
from __future__ import annotations

from typing import Any, Mapping

from ..models import MetricPredicate, Z3OwnerRule, Z3RuleSet
from ..z3_engine import Z3DiagnosisEngine


def build_coupled_solver_ruleset() -> Z3RuleSet:
    return Z3RuleSet(
        rules=(
            Z3OwnerRule(
                rule_id="pc_or_factorization_fail",
                owner_class="PC_OR_FACTORIZATION_FAIL",
                status="CLASSIFIED",
                decision_label="PC or factorization failure",
                priority=10,
                all_of=(MetricPredicate(metric_id="pc_failure", operator="gt", threshold=0.0),),
            ),
            Z3OwnerRule(
                rule_id="initial_nonfinite_fail",
                owner_class="INITIAL_NONFINITE_FAIL",
                status="CLASSIFIED",
                decision_label="initial non-finite residual failure",
                priority=20,
                all_of=(
                    MetricPredicate(
                        metric_id="nonfinite_residual_count", operator="gt", threshold=0.0
                    ),
                ),
            ),
            Z3OwnerRule(
                rule_id="scaling_dominated_fail",
                owner_class="SCALING_DOMINATED_FAIL",
                status="CLASSIFIED",
                decision_label="invalid automatic scaling",
                priority=30,
                all_of=(
                    MetricPredicate(
                        metric_id="scaling_invalid_count", operator="gt", threshold=0.0
                    ),
                ),
            ),
            Z3OwnerRule(
                rule_id="coupled_jacobian_or_residual_fail",
                owner_class="COUPLED_JACOBIAN_OR_RESIDUAL_FAIL",
                status="CLASSIFIED",
                decision_label="finite coupled residual runtime failure",
                priority=40,
                all_of=(
                    MetricPredicate(
                        metric_id="runtime_failure_with_finite_residuals",
                        operator="gt",
                        threshold=0.0,
                    ),
                ),
            ),
        ),
        pass_status="DIAGNOSTIC_INSUFFICIENT",
        rz_specific_status="NOT_APPLICABLE",
    )


def coupled_solver_metric_values(facts: Mapping[str, Any]) -> dict[str, float]:
    """Map canonical runtime evidence to scalar rule inputs."""
    linear_reason = facts.get("linear_reason")
    pc_hits = list(facts.get("pc_hits", []))
    nonfinite = list(facts.get("nonfinite_residuals", []))
    scaling_invalid = list(facts.get("scaling_invalid", []))
    residual_blocks = list(facts.get("variable_residuals", []))
    finite_residual_blocks = bool(residual_blocks) and not nonfinite
    return {
        "pc_failure": float(
            bool(pc_hits)
            or linear_reason in {"DIVERGED_PC_FAILED", "DIVERGED_PCSETUP_FAILED"}
        ),
        "nonfinite_residual_count": float(len(nonfinite)),
        "scaling_invalid_count": float(len(scaling_invalid)),
        "runtime_failure_with_finite_residuals": float(
            int(facts.get("returncode", 0)) != 0 and finite_residual_blocks
        ),
    }


def diagnose_coupled_runtime_evidence(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Classify coupled-solver evidence through the canonical Z3 path."""
    decision = Z3DiagnosisEngine(build_coupled_solver_ruleset()).diagnose(
        coupled_solver_metric_values(facts)
    )
    decision_class = decision.primary_owner_class or "DIAGNOSTIC_INSUFFICIENT"

    if decision_class == "PC_OR_FACTORIZATION_FAIL":
        if facts.get("pc_failure_reason") == "FACTOR_NUMERIC_ZEROPIVOT":
            reason = (
                "PETSc LU/preconditioner setup failed with FACTOR_NUMERIC_ZEROPIVOT; "
                "later nonlinear NAN/INF is downstream of the factorization failure"
            )
        else:
            reason = "the earliest direct linear-solver signature is PETSc preconditioner/setup failure"
    elif decision_class == "INITIAL_NONFINITE_FAIL":
        reason = "variable-residual diagnostics contain NaN/Inf without an earlier PC failure"
    elif decision_class == "SCALING_DOMINATED_FAIL":
        reason = "automatic scaling produced a zero or non-finite factor for a coupled variable"
    elif decision_class == "COUPLED_JACOBIAN_OR_RESIDUAL_FAIL":
        reason = (
            "runtime failed with finite per-variable residual evidence and without a direct "
            "PC/non-finite/scaling-invalid signature"
        )
    else:
        reason = "available invariant diagnostic signatures do not select a unique failure class"

    return {
        "class": decision_class,
        "reason": reason,
        **dict(facts),
    }


__all__ = [
    "build_coupled_solver_ruleset",
    "coupled_solver_metric_values",
    "diagnose_coupled_runtime_evidence",
]
