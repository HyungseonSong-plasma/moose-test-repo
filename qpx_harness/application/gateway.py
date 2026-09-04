"""Thin application gateway across canonical QPX semantic capabilities."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qpx_harness.adapters.moose import MooseTargetIR, lower_execution_plan
from qpx_harness.execution import ExecutionPlan, compile_execution_plan
from qpx_harness.ontology import OntologyService
from qpx_harness.ontology.model import DevelopmentState, ScientificPolicy
from qpx_harness.planning import default_capabilities, synthesize_policy
from qpx_harness.specification import SemanticCompilation, compile_experiment_intent, load_experiment_spec


@dataclass(frozen=True)
class PlannedExperiment:
    semantic: SemanticCompilation
    state: DevelopmentState
    policy: ScientificPolicy
    execution_plan: ExecutionPlan


def compile_experiment(path: str | Path, *, ontology: OntologyService | None = None) -> SemanticCompilation:
    ontology = ontology or OntologyService()
    spec = load_experiment_spec(path)
    return compile_experiment_intent(
        spec,
        capabilities=default_capabilities(),
        ontology=ontology,
    )


def plan_experiment(
    path: str | Path,
    *,
    state: DevelopmentState | None = None,
    ontology: OntologyService | None = None,
) -> PlannedExperiment:
    ontology = ontology or OntologyService()
    semantic = compile_experiment(path, ontology=ontology)
    state = state or DevelopmentState(
        state_id=f"state:{semantic.intent.experiment_id}:initial",
        case_id=semantic.intent.experiment_id,
        provenance_id=semantic.provenance.provenance_id,
    )
    ontology.commit_state(state)
    policy = synthesize_policy(state, semantic.intent, default_capabilities())
    ontology.register(policy)
    for action in policy.selected_actions:
        ontology.register(action)
    for decision in policy.decisions:
        ontology.register(decision)
    execution_plan = compile_execution_plan(policy)
    return PlannedExperiment(
        semantic=semantic,
        state=state,
        policy=policy,
        execution_plan=execution_plan,
    )


def lower_experiment(
    path: str | Path,
    *,
    state: DevelopmentState | None = None,
    ontology: OntologyService | None = None,
) -> tuple[PlannedExperiment, MooseTargetIR]:
    planned = plan_experiment(path, state=state, ontology=ontology)
    return planned, lower_execution_plan(planned.execution_plan)


__all__ = ["PlannedExperiment", "compile_experiment", "plan_experiment", "lower_experiment"]
