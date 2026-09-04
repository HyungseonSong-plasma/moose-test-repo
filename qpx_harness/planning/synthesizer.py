"""Deterministic solver-independent ScientificPolicy synthesis."""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

from qpx_harness.ontology.model import (
    ActionSpec,
    CapabilityDescriptor,
    DevelopmentState,
    ExperimentIntent,
    ScientificPolicy,
    SearchDecision,
)


def _stable_id(prefix: str, payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return f"{prefix}:{hashlib.sha256(blob.encode('utf-8')).hexdigest()[:16]}"


def _parameter_map(intent: ExperimentIntent) -> dict[str, object]:
    return dict(intent.parameters)


def _diffusion_actions(intent: ExperimentIntent) -> tuple[ActionSpec, ...]:
    params = _parameter_map(intent)
    requested = params.get("diffusivity", params.get("diffusion_coefficient", 1.0))
    preserves = tuple(
        item
        for item in (
            "drift_disabled",
            "joule_heating_disabled",
            "wall_energy_terms_held_fixed",
            "heavy_species_state_held_fixed",
            "poisson_feedback_held_fixed",
        )
    )
    control = ActionSpec(
        action_id=f"action:{intent.intent_id}:diffusion-control",
        intended_effect="establish controlled no-diffusion reference",
        target="electron_energy_transport",
        intervention_type="PARAMETER_CONTROL",
        discriminates=intent.target_ids,
        expected_information_gain=0.5,
        expected_cost=1.0,
        expected_risk=0.1,
        preserves=preserves,
        parameters=(("diffusivity", 0.0),),
    )
    treatment = ActionSpec(
        action_id=f"action:{intent.intent_id}:diffusion-treatment",
        intended_effect="apply requested controlled electron-energy diffusion",
        target="electron_energy_transport",
        intervention_type="PARAMETER_TREATMENT",
        discriminates=intent.target_ids,
        expected_information_gain=1.0,
        expected_cost=1.0,
        expected_risk=0.1,
        preserves=preserves,
        parameters=(("diffusivity", requested),),
    )
    return (control, treatment)


def _observability_action(intent: ExperimentIntent) -> tuple[ActionSpec, ...]:
    return (
        ActionSpec(
            action_id=f"action:{intent.intent_id}:observability",
            intended_effect="increase observability without changing intended physics",
            target="runtime_observability",
            intervention_type="OBSERVABILITY_INTERVENTION",
            discriminates=intent.target_ids,
            expected_information_gain=1.0,
            expected_cost=0.2,
            expected_risk=0.0,
            preserves=("physics", "scientific_controls", "solver_configuration"),
        ),
    )


def synthesize_policy(
    state: DevelopmentState,
    intent: ExperimentIntent,
    capabilities: Iterable[CapabilityDescriptor],
) -> ScientificPolicy:
    """Synthesize a bounded semantic policy without process execution or solver syntax."""
    capability_map = {item.capability_id: item for item in capabilities if item.available}
    unresolved = tuple(
        capability
        for capability in intent.requested_capabilities
        if capability not in capability_map
    )

    actions: list[ActionSpec] = []
    if "electron_energy_diffusion" in intent.requested_capabilities:
        if "electron_energy_diffusion" in capability_map:
            actions.extend(_diffusion_actions(intent))
    if "observability_instrumentation" in intent.requested_capabilities:
        if "observability_instrumentation" in capability_map:
            actions.extend(_observability_action(intent))

    # Generic capability requests that do not require a specialized reusable rule
    # still become semantic actions rather than target mutations.
    specialized = {"electron_energy_diffusion", "observability_instrumentation"}
    for capability in intent.requested_capabilities:
        if capability in unresolved or capability in specialized:
            continue
        actions.append(
            ActionSpec(
                action_id=f"action:{intent.intent_id}:{capability}",
                intended_effect=f"realize semantic capability {capability}",
                target=capability,
                intervention_type="SEMANTIC_CAPABILITY",
                discriminates=intent.target_ids,
                preserves=tuple(dict.fromkeys(str(item) for item in intent.constraint_ids)),
            )
        )

    decisions = tuple(
        SearchDecision(
            decision_id=f"decision:{action.action_id}",
            state_id=state.state_id,
            action_id=action.action_id,
            disposition="SELECTED",
            rationale=(
                "selected by deterministic capability synthesis for intent "
                f"{intent.intent_id}"
            ),
            constraint_ids=intent.constraint_ids,
        )
        for action in actions
    )

    held_fixed = tuple(intent.constraint_ids)
    required_observations = intent.requested_observations
    acceptance_requirements = tuple(
        f"evaluate target {target_id} with admitted evidence"
        for target_id in intent.target_ids
    )
    payload = {
        "state": state.state_id,
        "intent": intent.intent_id,
        "actions": [action.action_id for action in actions],
        "unresolved": unresolved,
    }
    policy_id = _stable_id("policy", payload)
    rationale = (
        "deterministic semantic capability synthesis"
        if not unresolved
        else "policy contains unresolved capability requirements"
    )
    return ScientificPolicy(
        policy_id=policy_id,
        source_state_id=state.state_id,
        source_intent_id=intent.intent_id,
        objective=intent.objective,
        selected_actions=tuple(actions),
        considered_actions=tuple(actions),
        decisions=decisions,
        held_fixed=held_fixed,
        required_observations=required_observations,
        acceptance_requirements=acceptance_requirements,
        required_capabilities=intent.requested_capabilities,
        unresolved_requirements=tuple(f"CAPABILITY_GAP:{item}" for item in unresolved),
        execution_bounds=intent.execution_bounds,
        rationale=rationale,
        provenance_id=intent.provenance_id,
    )


__all__ = ["synthesize_policy"]
