"""Thin application gateway across canonical Physics semantic capabilities."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from physics_harness.execution import ExecutionPlan, compile_execution_plan
from physics_harness.ontology import OntologyService
from physics_harness.ontology.records import DevelopmentState, ScientificPolicy
from physics_harness.ontology.sol_request import CanonicalRealizationModel, SolRequest, SolRequestCompiler
from physics_harness.ontology.sol_runtime_consumer import SolRuntimeOutcome, invoke_runtime_consumer
from physics_harness.planning import default_capabilities, synthesize_policy
from physics_harness.specification import SemanticCompilation, compile_experiment_intent, load_experiment_spec


@dataclass(frozen=True)
class PlannedExperiment:
    semantic: SemanticCompilation
    state: DevelopmentState
    policy: ScientificPolicy
    execution_plan: ExecutionPlan


@dataclass(frozen=True)
class SolPreparedExperiment:
    """Physics planning result plus the canonical request handed to SOL runtime."""

    planned: PlannedExperiment
    request: SolRequest


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


def prepare_sol_experiment(
    path: str | Path,
    *,
    realization_model: CanonicalRealizationModel,
    physics_capabilities: Sequence[str],
    capability_map: Mapping[str, str],
    backend_target: str,
    state: DevelopmentState | None = None,
    ontology: OntologyService | None = None,
) -> SolPreparedExperiment:
    """Compile explicit canonical owners into a SOL request without target inference.

    The caller must supply the reviewed realization model and capability mapping.
    ExecutionPlan spelling, tuple order, and local solver objects are deliberately
    not used to synthesize public-contract semantics.
    """
    planned = plan_experiment(path, state=state, ontology=ontology)
    request = SolRequestCompiler(capability_map, backend_target=backend_target).compile(
        realization_model,
        physics_capabilities=physics_capabilities,
    )
    return SolPreparedExperiment(planned=planned, request=request)


def run_sol_experiment(
    prepared: SolPreparedExperiment,
    *,
    consumer: Path,
    adapter: Path,
    timeout_seconds: float = 120.0,
) -> SolRuntimeOutcome:
    """Invoke the pinned SOL consumer; runtime completion is not scientific PASS."""
    return invoke_runtime_consumer(
        consumer,
        adapter,
        prepared.request,
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "PlannedExperiment",
    "SolPreparedExperiment",
    "compile_experiment",
    "plan_experiment",
    "prepare_sol_experiment",
    "run_sol_experiment",
]
