from __future__ import annotations

import json

import pytest

from qpx_harness.adapters.moose import emit_moose_input, lower_execution_plan
from qpx_harness.execution import compile_execution_plan
from qpx_harness.ontology import OntologyService, SemanticInvariantError
from qpx_harness.ontology.model import (
    DevelopmentState,
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
    validate_payload,
)


def _semantic_spec(tmp_path):
    source = tmp_path / "experiment.json"
    payload = {
        "schema_version": 2,
        "experiment_id": "controlled-electron-energy-diffusion",
        "objective": "validate controlled electron-energy diffusion",
        "target_claims": ["electron-energy diffusion smooths the profile"],
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
    }
    source.write_text(json.dumps(payload), encoding="utf-8")
    return source, payload


def test_canonical_spec_rejects_target_mutation_syntax(tmp_path):
    source, payload = _semantic_spec(tmp_path)
    payload["parameters"] = {"ensure_block": "FVKernels/electron_diffusion"}
    with pytest.raises(SpecSemanticError):
        validate_payload(payload, source_path=source)


def test_semantic_compilation_and_policy_are_deterministic(tmp_path):
    source, payload = _semantic_spec(tmp_path)
    spec = validate_payload(payload, source_path=source)
    capabilities = default_capabilities()
    first = compile_experiment_intent(spec, capabilities=capabilities)
    second = compile_experiment_intent(spec, capabilities=capabilities)
    assert first.intent == second.intent

    state = DevelopmentState(state_id="S0", case_id="case")
    policy1 = synthesize_policy(state, first.intent, capabilities)
    policy2 = synthesize_policy(state, first.intent, capabilities)
    assert policy1 == policy2
    rendered = repr(policy1)
    assert "FVKernels" not in rendered
    assert "FunctorMaterials" not in rendered
    assert "petsc_options" not in rendered


def test_execution_plan_is_solver_independent_and_lowering_is_deterministic(tmp_path):
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

    target1 = lower_execution_plan(plan)
    target2 = lower_execution_plan(plan)
    assert target1 == target2
    assert [emit_moose_input(case) for case in target1.cases] == [
        emit_moose_input(case) for case in target2.cases
    ]


def test_committed_state_is_immutable():
    service = OntologyService()
    state = DevelopmentState(state_id="S0", case_id="case")
    service.commit_state(state)
    with pytest.raises(SemanticInvariantError):
        service.commit_state(DevelopmentState(state_id="S0", case_id="case", repository=(("owner", "new"),)))


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
    s1 = DevelopmentState(state_id="S1", case_id="case", repository=(("canonical_owner", "ontology"),))
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
