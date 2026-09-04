"""Bounded semantic-state service for QPX_STATE_SEMANTICS_V1."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from typing import Any, Iterable

from .model import (
    ActionExecution,
    ActionSpec,
    Artifact,
    ClaimAssessment,
    DevelopmentState,
    DiagnosticConclusion,
    Evidence,
    ExperimentIntent,
    Hypothesis,
    HypothesisAssessment,
    Observation,
    ProvenanceRecord,
    StateDelta,
    StateTransition,
    SEMANTIC_CONTRACT_ID,
    ONTOLOGY_SCHEMA_VERSION,
)


class SemanticInvariantError(ValueError):
    pass


class SemanticVersionError(SemanticInvariantError):
    pass


class OntologyService:
    """Small in-memory semantic authority with deterministic persistence.

    Owlready2 is a projection backend (see :mod:`qpx_harness.ontology.owlready`),
    while this service owns closed-world commit invariants that OWL open-world
    semantics cannot safely enforce.
    """

    def __init__(self) -> None:
        self._objects: dict[str, Any] = {}
        self._states: dict[str, DevelopmentState] = {}
        self._transitions: dict[str, StateTransition] = {}

    @staticmethod
    def _identity(obj: Any) -> str:
        for name in (
            "state_id", "intent_id", "goal_id", "capability_id", "artifact_id",
            "observation_id", "evidence_id", "fact_id", "proposition_id",
            "assessment_id", "conclusion_id", "action_id", "decision_id",
            "policy_id", "execution_id", "outcome_id", "transition_id",
            "provenance_id", "constraint_id",
        ):
            value = getattr(obj, name, None)
            if value:
                return str(value)
        raise SemanticInvariantError(f"object has no stable semantic identity: {type(obj).__name__}")

    def register(self, obj: Any) -> Any:
        identity = self._identity(obj)
        prior = self._objects.get(identity)
        if prior is not None and prior != obj:
            raise SemanticInvariantError(f"identity collision for {identity!r}")
        self._objects[identity] = obj
        return obj

    def register_many(self, objects: Iterable[Any]) -> None:
        for obj in objects:
            self.register(obj)

    def get(self, identity: str) -> Any:
        return self._objects[identity]

    def maybe_get(self, identity: str) -> Any | None:
        return self._objects.get(identity)

    def commit_state(self, state: DevelopmentState) -> DevelopmentState:
        if state.semantic_contract != SEMANTIC_CONTRACT_ID:
            raise SemanticVersionError(
                f"state semantic contract {state.semantic_contract!r} != {SEMANTIC_CONTRACT_ID!r}"
            )
        prior = self._states.get(state.state_id)
        if prior is not None:
            if prior != state:
                raise SemanticInvariantError(
                    f"committed DevelopmentState {state.state_id!r} is immutable"
                )
            return prior
        self._validate_current_assessment_uniqueness(state)
        self._states[state.state_id] = state
        self.register(state)
        return state

    def _validate_current_assessment_uniqueness(self, state: DevelopmentState) -> None:
        hyp_keys: set[str] = set()
        for assessment_id in state.hypothesis_assessment_ids:
            assessment = self._objects.get(assessment_id)
            if not isinstance(assessment, HypothesisAssessment):
                raise SemanticInvariantError(
                    f"state references unregistered HypothesisAssessment {assessment_id!r}"
                )
            if assessment.state_id != state.state_id:
                raise SemanticInvariantError("hypothesis assessment belongs to another state")
            if assessment.hypothesis_id in hyp_keys:
                raise SemanticInvariantError(
                    f"multiple current assessments for hypothesis {assessment.hypothesis_id!r}"
                )
            hyp_keys.add(assessment.hypothesis_id)

        claim_keys: set[str] = set()
        for assessment_id in state.claim_assessment_ids:
            assessment = self._objects.get(assessment_id)
            if not isinstance(assessment, ClaimAssessment):
                raise SemanticInvariantError(
                    f"state references unregistered ClaimAssessment {assessment_id!r}"
                )
            if assessment.state_id != state.state_id:
                raise SemanticInvariantError("claim assessment belongs to another state")
            if assessment.claim_id in claim_keys:
                raise SemanticInvariantError(
                    f"multiple current assessments for claim {assessment.claim_id!r}"
                )
            claim_keys.add(assessment.claim_id)

    def commit_transition(self, transition: StateTransition) -> StateTransition:
        if transition.predecessor_id not in self._states:
            raise SemanticInvariantError("transition predecessor is not committed")
        if transition.successor_id not in self._states:
            raise SemanticInvariantError("transition successor is not committed")
        prior = self._transitions.get(transition.transition_id)
        if prior is not None and prior != transition:
            raise SemanticInvariantError("transition identity collision")
        self._transitions[transition.transition_id] = transition
        self.register(transition)
        return transition

    def current_state(self, case_id: str) -> DevelopmentState | None:
        states = [state for state in self._states.values() if state.case_id == case_id]
        if not states:
            return None
        successors = {t.predecessor_id for t in self._transitions.values() if self._states[t.predecessor_id].case_id == case_id}
        leaves = [state for state in states if state.state_id not in successors]
        if len(leaves) == 1:
            return leaves[0]
        if len(states) == 1:
            return states[0]
        return sorted(leaves or states, key=lambda item: item.state_id)[-1]

    def proposition_assessment_history(self, proposition_id: str) -> tuple[Any, ...]:
        values = [
            obj for obj in self._objects.values()
            if isinstance(obj, (HypothesisAssessment, ClaimAssessment))
            and getattr(obj, "hypothesis_id", getattr(obj, "claim_id", None)) == proposition_id
        ]
        return tuple(sorted(values, key=lambda item: (item.state_id, item.assessment_id)))

    def provenance_chain(self, identity: str) -> tuple[Any, ...]:
        start = self.get(identity)
        provenance_id = getattr(start, "provenance_id", None)
        if not provenance_id:
            return (start,)
        provenance = self._objects.get(provenance_id)
        if not isinstance(provenance, ProvenanceRecord):
            return (start,)
        artifacts = tuple(
            self._objects[item]
            for item in provenance.artifact_ids
            if item in self._objects
        )
        return (start, provenance, *artifacts)

    def state_transitions(self, case_id: str) -> tuple[StateTransition, ...]:
        values = [
            transition for transition in self._transitions.values()
            if self._states[transition.predecessor_id].case_id == case_id
        ]
        return tuple(sorted(values, key=lambda item: item.transition_id))

    @staticmethod
    def _serialize(obj: Any) -> Any:
        if is_dataclass(obj):
            payload = asdict(obj)
            payload["__type__"] = type(obj).__name__
            return payload
        raise TypeError(type(obj).__name__)

    def save_json(self, path: str | Path) -> Path:
        target = Path(path)
        payload = {
            "semantic_contract": SEMANTIC_CONTRACT_ID,
            "ontology_schema_version": ONTOLOGY_SCHEMA_VERSION,
            "objects": [self._serialize(obj) for _, obj in sorted(self._objects.items())],
        }
        target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        return target

    def project_to_owlready(self, *, world: Any | None = None) -> Any:
        """Project registered objects into an explicit Owlready2 World lazily."""
        from .owlready import Owlready2Projection

        projection = Owlready2Projection(world=world)
        projection.materialize(self._objects.values())
        return projection


__all__ = ["OntologyService", "SemanticInvariantError", "SemanticVersionError"]
