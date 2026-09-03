"""Generic Z3 SMT decision engine for externally supplied diagnosis rules."""
from __future__ import annotations

import math
from collections.abc import Mapping

import z3

from .models import (
    DiagnosisRuleRegistry,
    MetricPredicate,
    Z3Decision,
    Z3OwnerRule,
    Z3RuleSet,
)


def _real_value(value: float) -> z3.RatNumRef:
    """Represent a finite Python float as a stable decimal rational in Z3."""
    if not math.isfinite(value):
        raise ValueError("Z3 metric values must be finite")
    return z3.RealVal(format(value, ".17g"))


def _predicate_expr(
    predicate: MetricPredicate,
    metric_vars: Mapping[str, z3.ArithRef],
) -> z3.BoolRef:
    variable = metric_vars[predicate.metric_id]
    threshold = _real_value(predicate.threshold)
    return {
        "gt": variable > threshold,
        "ge": variable >= threshold,
        "lt": variable < threshold,
        "le": variable <= threshold,
        "eq": variable == threshold,
        "ne": variable != threshold,
    }[predicate.operator]


def ruleset_from_registry(registry: DiagnosisRuleRegistry) -> Z3RuleSet:
    """Adapt legacy single-metric registry rules to the Z3 rule-set contract."""
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


class Z3DiagnosisEngine:
    """Evaluate externally injected logical owner rules with Z3.

    The engine never substitutes zero for missing evidence. Every metric referenced
    by the rule set must be supplied explicitly, and every value must be finite.
    Candidate rules may overlap; deterministic priority is encoded in the SMT
    model so exactly one selected owner or the PASS state is active.
    """

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

        solver = z3.Solver()
        metric_vars = {
            metric_id: z3.Real(f"metric::{metric_id}")
            for metric_id in sorted(self.ruleset.required_metric_ids)
        }
        for metric_id, value in values.items():
            solver.add(metric_vars[metric_id] == _real_value(value))

        ordered = self.ruleset.ordered_rules
        candidate_vars: dict[str, z3.BoolRef] = {}
        selected_vars: dict[str, z3.BoolRef] = {}
        previous_candidates: list[z3.BoolRef] = []

        for rule in ordered:
            all_expr = z3.And(
                *[_predicate_expr(p, metric_vars) for p in rule.all_of]
            ) if rule.all_of else z3.BoolVal(True)
            any_expr = z3.Or(
                *[_predicate_expr(p, metric_vars) for p in rule.any_of]
            ) if rule.any_of else z3.BoolVal(True)
            none_expr = z3.And(
                *[z3.Not(_predicate_expr(p, metric_vars)) for p in rule.none_of]
            ) if rule.none_of else z3.BoolVal(True)

            candidate = z3.Bool(f"candidate::{rule.rule_id}")
            solver.add(candidate == z3.And(all_expr, any_expr, none_expr))
            candidate_vars[rule.rule_id] = candidate

            selected = z3.Bool(f"selected::{rule.rule_id}")
            no_higher_priority = (
                z3.Not(z3.Or(*previous_candidates))
                if previous_candidates
                else z3.BoolVal(True)
            )
            solver.add(selected == z3.And(candidate, no_higher_priority))
            selected_vars[rule.rule_id] = selected
            previous_candidates.append(candidate)

        pass_var = z3.Bool("diagnosis::pass")
        solver.add(
            pass_var
            == (
                z3.Not(z3.Or(*candidate_vars.values()))
                if candidate_vars
                else z3.BoolVal(True)
            )
        )
        solver.add(
            z3.PbEq(
                [(selected, 1) for selected in selected_vars.values()] + [(pass_var, 1)],
                1,
            )
        )

        result = solver.check()
        if result == z3.unsat:
            return Z3Decision(
                solver_status="UNSATISFIABLE",
                status="UNSATISFIABLE",
            )
        if result == z3.unknown:
            return Z3Decision(
                solver_status="UNKNOWN",
                status="UNKNOWN",
                z3_model=solver.reason_unknown(),
            )

        model = solver.model()
        for rule in ordered:
            if z3.is_true(model.eval(selected_vars[rule.rule_id], model_completion=True)):
                return Z3Decision(
                    solver_status="SATISFIED",
                    primary_owner_class=rule.owner_class,
                    selected_rule_id=rule.rule_id,
                    status=rule.status,
                    z3_model=str(model),
                )

        if not z3.is_true(model.eval(pass_var, model_completion=True)):
            raise RuntimeError("Z3 model satisfied but selected neither owner nor PASS")
        return Z3Decision(
            solver_status="SATISFIED",
            primary_owner_class=None,
            selected_rule_id=None,
            status=self.ruleset.pass_status,
            z3_model=str(model),
        )
