from __future__ import annotations

from pathlib import Path

import owlready2

from qpx_harness.adapters.moose import emit_moose_input, lower_execution_plan
from qpx_harness.execution import compile_execution_plan
from qpx_harness.ontology import OntologyService
from qpx_harness.ontology.records import (
    DevelopmentState,
    ONTOLOGY_SCHEMA_VERSION,
    SEMANTIC_CONTRACT_ID,
)
from qpx_harness.ontology.owlready import ONTOLOGY_IRI, Owlready2Projection
from qpx_harness.planning import default_capabilities, synthesize_policy
from qpx_harness.specification import compile_experiment_intent, load_experiment_spec


ROOT = Path(__file__).resolve().parents[2]
E2A_SPEC = ROOT / "experiments" / "semantic" / "electron_energy_diffusion" / "experiment.json"


def _accepted_pipeline():
    spec = load_experiment_spec(E2A_SPEC)
    capabilities = default_capabilities()
    ontology = OntologyService()
    compilation = compile_experiment_intent(
        spec,
        capabilities=capabilities,
        ontology=ontology,
    )
    state = DevelopmentState(state_id="S-E2A-ACCEPTANCE", case_id="e2a-acceptance")
    ontology.commit_state(state)
    policy = synthesize_policy(state, compilation.intent, capabilities)
    ontology.register(policy)
    ontology.register_many(policy.selected_actions)
    ontology.register_many(policy.decisions)
    plan = compile_execution_plan(policy)
    target = lower_execution_plan(plan)
    return spec, compilation, state, policy, plan, target, ontology


def test_owlready2_world_is_explicit_isolated_and_persistable(tmp_path):
    first = Owlready2Projection(world=owlready2.World())
    second = Owlready2Projection(world=owlready2.World())

    assert first.world is not owlready2.default_world
    assert second.world is not owlready2.default_world
    assert first.world is not second.world

    state = DevelopmentState(state_id="owlready-acceptance-state", case_id="case")
    first.materialize((state,))
    individual_iri = f"{ONTOLOGY_IRI}owlready_acceptance_state"

    projected = first.world[individual_iri]
    assert projected is not None
    assert second.world[individual_iri] is None
    assert projected.semantic_contract == SEMANTIC_CONTRACT_ID
    assert projected.schema_version == ONTOLOGY_SCHEMA_VERSION

    persisted = tmp_path / "qpx-ontology.owl"
    first.save(str(persisted))

    reloaded_world = owlready2.World()
    reloaded_world.get_ontology(persisted.resolve().as_uri()).load()
    reloaded = reloaded_world[individual_iri]
    assert reloaded is not None
    assert reloaded.semantic_id == state.state_id
    assert reloaded.semantic_contract == SEMANTIC_CONTRACT_ID
    assert reloaded.schema_version == ONTOLOGY_SCHEMA_VERSION


def test_q10_intent_lineage_is_deterministic_and_read_only():
    spec, compilation, _state, _policy, _plan, _target, ontology = _accepted_pipeline()
    before = ontology.objects()

    def query():
        intent = ontology.intent(compilation.intent.intent_id)
        goals = tuple(ontology.get(identity) for identity in intent.goal_ids)
        targets = tuple(ontology.get(identity) for identity in intent.target_ids)
        provenance = ontology.provenance_chain(intent.intent_id)
        return intent, goals, targets, provenance

    first = query()
    second = query()

    assert first == second
    assert ontology.objects() == before
    intent, goals, targets, provenance = first
    assert compilation.source_spec_identity == str(spec.source_path)
    assert intent == compilation.intent
    assert goals == compilation.goals
    assert targets == (*compilation.target_claims, *compilation.target_questions)
    assert intent.provenance_id == compilation.provenance.provenance_id
    assert provenance[0] == intent
    assert provenance[1] == compilation.provenance
    assert compilation.provenance.source_identity == str(spec.source_path)


def test_q11_policy_lineage_preserves_state_intent_capabilities_and_rationale():
    _spec, compilation, state, policy, _plan, _target, ontology = _accepted_pipeline()
    before = ontology.objects()

    def query():
        policies = ontology.policies(
            state_id=state.state_id,
            intent_id=compilation.intent.intent_id,
        )
        actions = tuple(ontology.action(action.action_id) for action in policy.selected_actions)
        decisions = ontology.search_decisions(state.state_id)
        return ontology.current_state(state.case_id), policies, actions, decisions

    first = query()
    second = query()

    assert first == second
    assert ontology.objects() == before
    current_state, policies, actions, decisions = first
    assert current_state == state
    assert policies == (policy,)
    assert policy.source_state_id == state.state_id
    assert policy.source_intent_id == compilation.intent.intent_id
    assert policy.required_capabilities == compilation.intent.requested_capabilities
    assert actions == policy.selected_actions
    assert decisions == policy.decisions
    assert policy.rationale
    assert policy.unresolved_requirements == ()


def test_q12_execution_lineage_preserves_policy_plan_and_target_identity():
    _spec, _compilation, _state, policy, plan, target, _ontology = _accepted_pipeline()

    assert plan.source_policy_id == policy.policy_id
    assert target.source_plan_id == plan.plan_id
    assert plan.model == policy.model == target.model
    assert tuple(case.action_id for case in plan.cases) == tuple(
        action.action_id for action in policy.selected_actions
    )
    assert tuple(case.action_id for case in target.cases) == tuple(
        case.action_id for case in plan.cases
    )
    assert tuple(case.case_id for case in target.cases) == tuple(
        case.case_id for case in plan.cases
    )

    first_emission = tuple(emit_moose_input(case) for case in target.cases)
    second_target = lower_execution_plan(plan)
    second_emission = tuple(emit_moose_input(case) for case in second_target.cases)

    assert second_target == target
    assert second_emission == first_emission
    assert policy.source_intent_id
    assert policy.source_state_id
