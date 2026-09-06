from __future__ import annotations

import json
from pathlib import Path

import pytest

from qpx_harness.adapters.moose import (
    MooseLoweringError,
    emit_moose_input,
    lower_execution_plan,
)
from qpx_harness.execution import compile_execution_plan
from qpx_harness.execution.plan import ExecutionCase, ExecutionPlan
from qpx_harness.ontology import (
    OntologyService,
    SemanticInvariantError,
    SemanticVersionError,
)
from qpx_harness.ontology.records import (
    DevelopmentState,
    ExperimentIntent,
    Hypothesis,
    HypothesisAssessment,
    HypothesisSupport,
    StateDelta,
    StateTransition,
)
from qpx_harness.planning import default_capabilities, synthesize_policy
from qpx_harness.specification import (
    SpecSemanticError,
    compile_experiment_intent,
    load_experiment_spec,
    validate_payload,
)

ROOT = Path(__file__).resolve().parents[2]


def _semantic_spec(tmp_path):
    source = tmp_path / "experiment.json"
    payload = {
        "schema_version": 2,
        "experiment_id": "controlled-electron-energy-diffusion",
        "objective": "validate controlled electron-energy diffusion",
        "model": "oxygen_icp_electron_energy",
        "target_claims": ["electron-energy diffusion smooths the profile"],
        "target_questions": ["does the closed-boundary inventory remain conserved?"],
        "requested_capabilities": [
            "electron_energy_diffusion",
            "electron_energy_inventory_observation",
        ],
        "parameters": {"diffusivity": 0.25},
        "constraints": [
            "drift disabled",
            "Joule heating disabled",
            "heavy state held fixed",
        ],
        "observations": ["energy_inventory", "energy_profile"],
        "execution_bounds": {"max_steps": 5},
        "cases": [
            {
                "case_id": "requested-diffusion",
                "parameters": {"diffusivity": 0.25},
                "constraints": ["same mesh and time-step as control"],
            }
        ],
        "provenance": {"historical_source": "Issue26 E2a semantic migration"},
    }
    source.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return source, payload


def test_canonical_spec_rejects_target_mutation_syntax(tmp_path):
    source, payload = _semantic_spec(tmp_path)
    payload["parameters"] = {"ensure_block": "FVKernels/electron_diffusion"}
    with pytest.raises(SpecSemanticError):
        validate_payload(payload, source_path=source)


def test_semantic_compilation_preserves_spec_meaning(tmp_path):
    source, payload = _semantic_spec(tmp_path)
    spec = validate_payload(payload, source_path=source)
    service = OntologyService()
    compilation = compile_experiment_intent(
        spec,
        capabilities=default_capabilities(),
        ontology=service,
    )

    assert compilation.intent.model == "oxygen_icp_electron_energy"
    assert tuple(goal.statement for goal in compilation.goals) == (payload["objective"],)
    assert tuple(claim.statement for claim in compilation.target_claims) == tuple(
        payload["target_claims"]
    )
    assert tuple(question.statement for question in compilation.target_questions) == tuple(
        payload["target_questions"]
    )
    assert len(compilation.cases) == 1
    assert compilation.cases[0].parameters == (("diffusivity", 0.25),)
    assert compilation.intent.case_ids == (compilation.cases[0].case_id,)
    assert set(compilation.intent.target_ids) == {
        compilation.target_claims[0].proposition_id,
        compilation.target_questions[0].question_id,
    }
    assert compilation.intent.goal_ids != compilation.intent.target_ids
    assert dict(compilation.provenance.metadata)["historical_source"] == (
        "Issue26 E2a semantic migration"
    )
    assert service.get(compilation.target_claims[0].proposition_id) == compilation.target_claims[0]
    assert service.get(compilation.target_questions[0].question_id) == compilation.target_questions[0]


def test_semantic_compilation_and_policy_are_deterministic(tmp_path):
    source, payload = _semantic_spec(tmp_path)
    spec = validate_payload(payload, source_path=source)
    capabilities = default_capabilities()
    first = compile_experiment_intent(spec, capabilities=capabilities)
    second = compile_experiment_intent(spec, capabilities=capabilities)
    assert first == second

    state = DevelopmentState(state_id="S0", case_id="case")
    policy1 = synthesize_policy(state, first.intent, capabilities)
    policy2 = synthesize_policy(state, first.intent, capabilities)
    assert policy1 == policy2
    assert len(policy1.selected_actions) == 2
    assert {action.intervention_type for action in policy1.selected_actions} == {
        "PARAMETER_CONTROL",
        "PARAMETER_TREATMENT",
    }
    assert all(action.preserves == first.intent.constraint_ids for action in policy1.selected_actions)
    assert policy1.model == first.intent.model
    assert policy1.target_ids == first.intent.target_ids
    assert "controlled-electron-energy-diffusion:v1" in policy1.policy_rule_ids
    rendered = repr(policy1)
    assert "FVKernels" not in rendered
    assert "FunctorMaterials" not in rendered
    assert "petsc_options" not in rendered


def test_execution_plan_is_solver_independent_and_lowering_is_concrete(tmp_path):
    source, payload = _semantic_spec(tmp_path)
    spec = validate_payload(payload, source_path=source)
    capabilities = default_capabilities()
    compilation = compile_experiment_intent(spec, capabilities=capabilities)
    state = DevelopmentState(state_id="S0", case_id="case")
    policy = synthesize_policy(state, compilation.intent, capabilities)
    plan = compile_execution_plan(policy)
    text = repr(plan)
    assert "FVKernels" not in text
    assert "Executioner" not in text
    assert "petsc_options" not in text
    assert plan.model == "oxygen_icp_electron_energy"
    assert {case.target for case in plan.cases} == {"electron_energy_transport"}

    target1 = lower_execution_plan(plan)
    target2 = lower_execution_plan(plan)
    assert target1 == target2
    emitted = [emit_moose_input(case) for case in target1.cases]
    assert emitted == [emit_moose_input(case) for case in target2.cases]
    assert all("[FVKernels]" in item for item in emitted)
    assert all("  [n_epsilon_time]" in item for item in emitted)
    assert all("  [qpx_n_epsilon_diffusion]" in item for item in emitted)
    assert all("type = FVDiffusion" in item for item in emitted)
    assert all("type = FVTimeKernel" in item for item in emitted)
    assert all("  [electron_energy_density_J_m3]" in item for item in emitted)
    assert all("  [mean_en_solved]" in item for item in emitted)
    assert all("  [electron_energy_inventory_J]" in item for item in emitted)
    assert all("functor = electron_energy_density_J_m3" in item for item in emitted)
    assert all("  [n_epsilon_min]" in item for item in emitted)
    assert all("  [n_epsilon_max]" in item for item in emitted)
    assert all("  [mean_en_solved_avg]" in item for item in emitted)
    assert all("num_steps = 5" in item for item in emitted)
    assert all("[QPX]" not in item for item in emitted)
    assert all("n_epsilon_drift" not in item for item in emitted)
    assert all("joule_source" not in item.lower() for item in emitted)
    assert all("[Variables/n_epsilon]" not in item for item in emitted)


def test_accepted_semantic_e2a_fixture_matches_frozen_control_values():
    spec = load_experiment_spec(
        ROOT / "experiments" / "semantic" / "electron_energy_diffusion" / "experiment.json"
    )
    assert dict(spec.parameters)["diffusivity"] == 100.0
    assert dict(spec.execution_bounds) == {
        "dt": 1e-8,
        "end_time": 1e-8,
        "max_steps": 1,
    }
    compilation = compile_experiment_intent(spec, capabilities=default_capabilities())
    policy = synthesize_policy(
        DevelopmentState(state_id="S0", case_id="accepted-e2a"),
        compilation.intent,
        default_capabilities(),
    )
    plan = compile_execution_plan(policy)
    target = lower_execution_plan(plan)
    emitted = [emit_moose_input(case) for case in target.cases]
    assert len(emitted) == 2
    assert any("prop_values = '0'" in item for item in emitted)
    assert any("prop_values = '100'" in item for item in emitted)
    assert all("dt = 1e-08" in item for item in emitted)
    assert all("end_time = 1e-08" in item for item in emitted)
    assert all("num_steps = 1" in item for item in emitted)
    assert all("${n_e_value}*5.7327599999999999" in item for item in emitted)
    assert all("1.6021766339999999e-19" in item for item in emitted)


def test_unknown_semantic_action_does_not_emit_placeholder_target():
    plan = ExecutionPlan(
        plan_id="P",
        source_policy_id="POL",
        cases=(
            ExecutionCase(
                case_id="C",
                action_id="A",
                target="unsupported_semantic_target",
                intervention_type="SEMANTIC_CAPABILITY",
            ),
        ),
    )
    with pytest.raises(MooseLoweringError, match="no approved MOOSE realization"):
        lower_execution_plan(plan)


def test_quasi_neutral_policy_derivation_is_state_based_and_solver_independent():
    state = DevelopmentState(
        state_id="S0",
        case_id="case",
        system=(("signed_heavy_charge_number_density_m3", 2.5e15),),
    )
    intent = ExperimentIntent(
        intent_id="I",
        experiment_id="qn",
        objective="derive quasi-neutral electron reference",
        model="oxygen_icp",
        requested_capabilities=("quasi_neutral_initialization",),
    )
    policy = synthesize_policy(state, intent, default_capabilities())
    assert policy.unresolved_requirements == ()
    assert policy.derived_values == (("electron_reference_density_m3", 2.5e15),)
    assert len(policy.selected_actions) == 1
    assert policy.selected_actions[0].intervention_type == "DERIVED_INITIALIZATION"
    assert "MOOSE" not in repr(policy)

    plan = compile_execution_plan(policy)
    target = lower_execution_plan(plan)
    emitted = emit_moose_input(target.cases[0])
    assert "n_e_value = 2500000000000000" in emitted
    assert "[QPX]" not in emitted


def test_committed_state_is_immutable():
    service = OntologyService()
    state = DevelopmentState(state_id="S0", case_id="case")
    service.commit_state(state)
    with pytest.raises(SemanticInvariantError):
        service.commit_state(
            DevelopmentState(
                state_id="S0",
                case_id="case",
                repository=(("owner", "new"),),
            )
        )


def test_one_current_hypothesis_assessment_per_state():
    service = OntologyService()
    hypothesis = Hypothesis(proposition_id="H1", statement="candidate cause")
    a1 = HypothesisAssessment(
        assessment_id="A1",
        hypothesis_id="H1",
        state_id="S0",
        support=HypothesisSupport.PLAUSIBLE,
    )
    a2 = HypothesisAssessment(
        assessment_id="A2",
        hypothesis_id="H1",
        state_id="S0",
        support=HypothesisSupport.SUPPORTED,
    )
    service.register_many((hypothesis, a1, a2))
    with pytest.raises(SemanticInvariantError):
        service.commit_state(
            DevelopmentState(
                state_id="S0",
                case_id="case",
                hypothesis_assessment_ids=("A1", "A2"),
            )
        )


def test_repository_only_state_delta_is_first_class():
    service = OntologyService()
    s0 = DevelopmentState(state_id="S0", case_id="case")
    s1 = DevelopmentState(
        state_id="S1",
        case_id="case",
        repository=(("canonical_owner", "ontology"),),
    )
    service.commit_state(s0)
    service.commit_state(s1)
    transition = StateTransition(
        transition_id="T0",
        predecessor_id="S0",
        successor_id="S1",
        delta=StateDelta(repository_delta=(("canonical_owner", "ontology"),)),
    )
    service.commit_transition(transition)
    assert transition.delta.repository_delta
    assert transition.delta.world_delta == ()
    assert transition.delta.epistemic_delta == ()


def test_ontology_json_round_trip_reconstructs_typed_semantics(tmp_path):
    source, payload = _semantic_spec(tmp_path)
    spec = validate_payload(payload, source_path=source)
    service = OntologyService()
    compilation = compile_experiment_intent(
        spec,
        capabilities=default_capabilities(),
        ontology=service,
    )
    s0 = DevelopmentState(state_id="S0", case_id="case")
    s1 = DevelopmentState(
        state_id="S1",
        case_id="case",
        repository=(("canonical_owner", "ontology"),),
    )
    service.commit_state(s0)
    policy = synthesize_policy(s0, compilation.intent, default_capabilities())
    service.register(policy)
    service.register_many(policy.selected_actions)
    service.register_many(policy.decisions)
    service.commit_state(s1)
    transition = StateTransition(
        transition_id="T0",
        predecessor_id="S0",
        successor_id="S1",
        delta=StateDelta(repository_delta=(("canonical_owner", "ontology"),)),
    )
    service.commit_transition(transition)

    persisted = service.save_json(tmp_path / "ontology.json")
    reloaded = OntologyService.load_json(persisted)
    assert reloaded.get(compilation.intent.intent_id) == compilation.intent
    assert reloaded.get(compilation.target_claims[0].proposition_id) == compilation.target_claims[0]
    assert reloaded.get(compilation.target_questions[0].question_id) == compilation.target_questions[0]
    assert reloaded.get(policy.policy_id) == policy
    assert reloaded.current_state("case") == s1
    assert reloaded.state_transitions("case") == (transition,)


def test_ontology_json_round_trip_rejects_incompatible_version(tmp_path):
    service = OntologyService()
    service.commit_state(DevelopmentState(state_id="S0", case_id="case"))
    persisted = service.save_json(tmp_path / "ontology.json")
    payload = json.loads(persisted.read_text(encoding="utf-8"))
    payload["semantic_contract"] = "QPX_STATE_SEMANTICS_V0"
    persisted.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SemanticVersionError):
        OntologyService.load_json(persisted)


def test_owlready_worlds_are_isolated_when_available():
    owlready2 = pytest.importorskip("owlready2")
    from qpx_harness.ontology.owlready import Owlready2Projection

    first = Owlready2Projection(world=owlready2.World())
    second = Owlready2Projection(world=owlready2.World())
    assert first.world is not second.world
    state = DevelopmentState(state_id="isolated-state", case_id="case")
    first.materialize((state,))
    assert first.world["https://qpx.local/ontology/development-state/v1#isolated_state"] is not None
    assert second.world["https://qpx.local/ontology/development-state/v1#isolated_state"] is None
