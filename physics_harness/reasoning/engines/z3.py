"""Z3 backend mechanics for backend-neutral reasoning rules."""
from __future__ import annotations

from typing import Mapping

from physics_harness.reasoning.diagnosis import ReasoningDecision
from physics_harness.reasoning.rules import MetricPredicate, ReasoningRule, RuleSet


class Z3BackendUnavailable(RuntimeError):
    pass


def _predicate_expr(z3, variable, predicate: MetricPredicate):
    op = predicate.operator
    threshold = predicate.threshold
    if op == "gt": return variable > threshold
    if op == "ge": return variable >= threshold
    if op == "lt": return variable < threshold
    if op == "le": return variable <= threshold
    if op == "eq": return variable == threshold
    if op == "ne": return variable != threshold
    raise ValueError(f"unsupported predicate operator: {op}")


def evaluate_rules(metrics: Mapping[str, float], rules: RuleSet) -> ReasoningDecision:
    """Evaluate neutral rules using Z3 without owning scientific meaning."""
    try:
        import z3
    except ImportError as exc:  # pragma: no cover - optional backend
        raise Z3BackendUnavailable("Z3 backend requested but z3-solver is unavailable") from exc

    missing = sorted(rules.required_metric_ids - set(metrics))
    if missing:
        raise ValueError("missing metric(s) required by rule set: " + ", ".join(missing))

    variables = {name: z3.Real(name) for name in rules.required_metric_ids}
    solver = z3.Solver()
    for name, value in metrics.items():
        if name in variables:
            solver.add(variables[name] == z3.RealVal(str(value)))

    matched: list[ReasoningRule] = []
    for rule in rules.ordered_rules:
        terms = []
        if rule.all_of:
            terms.append(z3.And(*[_predicate_expr(z3, variables[p.metric_id], p) for p in rule.all_of]))
        if rule.any_of:
            terms.append(z3.Or(*[_predicate_expr(z3, variables[p.metric_id], p) for p in rule.any_of]))
        if rule.none_of:
            terms.append(z3.Not(z3.Or(*[_predicate_expr(z3, variables[p.metric_id], p) for p in rule.none_of])))
        rule_expr = z3.And(*terms) if terms else z3.BoolVal(False)
        probe = z3.Solver()
        probe.add(*solver.assertions())
        probe.add(rule_expr)
        if probe.check() == z3.sat:
            matched.append(rule)

    if not matched:
        status = solver.check()
        if status == z3.unknown:
            return ReasoningDecision(solver_status="UNKNOWN", status="UNKNOWN")
        return ReasoningDecision(solver_status="SATISFIED", status=rules.pass_status)

    selected = matched[0]
    solver_status = solver.check()
    model = str(solver.model()) if solver_status == z3.sat else None
    return ReasoningDecision(
        solver_status="SATISFIED" if solver_status == z3.sat else str(solver_status).upper(),
        status=selected.status,
        primary_owner_class=selected.owner_class,
        selected_rule_id=selected.rule_id,
        backend_model=model,
    )


__all__ = ["Z3BackendUnavailable", "evaluate_rules"]
