"""Bounded semantic-state service for QPX_STATE_SEMANTICS_V1."""
from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from enum import Enum
import json
from pathlib import Path
import types
from typing import Any, Iterable, Union, get_args, get_origin, get_type_hints

from . import model as semantic_model
from .model import (
    ActionSpec,
    CapabilityDescriptor,
    ClaimAssessment,
    DevelopmentState,
    ExperimentIntent,
    HypothesisAssessment,
    ProvenanceRecord,
    ScientificPolicy,
    SearchDecision,
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

    _IDENTITY_FIELD_BY_TYPE = {
        "ProvenanceRecord": "provenance_id",
        "Artifact": "artifact_id",
        "Observation": "observation_id",
        "Evidence": "evidence_id",
        "DerivedFact": "fact_id",
        "Constraint": "constraint_id",
        "DevelopmentGoal": "goal_id",
        "Proposition": "proposition_id",
        "Hypothesis": "proposition_id",
        "MechanismClaim": "proposition_id",
        "ValidationClaim": "proposition_id",
        "OpenQuestion": "question_id",
        "HypothesisAssessment": "assessment_id",
        "ClaimAssessment": "assessment_id",
        "DiagnosticConclusion": "conclusion_id",
        "CapabilityDescriptor": "capability_id",
        "ExperimentCaseIntent": "case_id",
        "ExperimentIntent": "intent_id",
        "ActionSpec": "action_id",
        "SearchDecision": "decision_id",
        "ScientificPolicy": "policy_id",
        "DevelopmentState": "state_id",
        "StateTransition": "transition_id",
        "ActionExecution": "execution_id",
        "ExecutionOutcome": "outcome_id",
    }

    def __init__(self) -> None:
        self._objects: dict[str, Any] = {}
        self._states: dict[str, DevelopmentState] = {}
        self._transitions: dict[str, StateTransition] = {}

    @classmethod
    def _identity(cls, obj: Any) -> str:
        """Return the object's owned identity, never an identity it references.

        Semantic records contain many ``*_id`` references. Selecting the first
        non-empty field is unsafe because, for example, an Observation may
        reference an Artifact and a SearchDecision references a State. Identity
        ownership is therefore explicit per semantic record type.
        """
        field_name = cls._IDENTITY_FIELD_BY_TYPE.get(type(obj).__name__)
        if field_name is None:
            raise SemanticInvariantError(
                f"object type has no registered stable semantic identity: {type(obj).__name__}"
            )
        value = getattr(obj, field_name, None)
        if value is None or str(value) == "":
            raise SemanticInvariantError(
                f"object has empty stable semantic identity: {type(obj).__name__}.{field_name}"
            )
        return str(value)

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

    def objects(self, semantic_type: type[Any] | None = None) -> tuple[Any, ...]:
        """Return a deterministic read-only snapshot of registered semantic objects."""
        values: Iterable[Any] = self._objects.values()
        if semantic_type is not None:
            values = (obj for obj in values if isinstance(obj, semantic_type))
        return tuple(sorted(values, key=self._identity))

    def intent(self, intent_id: str) -> ExperimentIntent:
        value = self.get(intent_id)
        if not isinstance(value, ExperimentIntent):
            raise KeyError(f"{intent_id!r} is not an ExperimentIntent")
        return value

    def capability(self, capability_id: str) -> CapabilityDescriptor:
        value = self.get(capability_id)
        if not isinstance(value, CapabilityDescriptor):
            raise KeyError(f"{capability_id!r} is not a CapabilityDescriptor")
        return value

    def policies(
        self,
        *,
        state_id: str | None = None,
        intent_id: str | None = None,
    ) -> tuple[ScientificPolicy, ...]:
        values = [
            obj
            for obj in self._objects.values()
            if isinstance(obj, ScientificPolicy)
            and (state_id is None or obj.source_state_id == state_id)
            and (intent_id is None or obj.source_intent_id == intent_id)
        ]
        return tuple(sorted(values, key=lambda item: item.policy_id))

    def policy(self, policy_id: str) -> ScientificPolicy:
        value = self.get(policy_id)
        if not isinstance(value, ScientificPolicy):
            raise KeyError(f"{policy_id!r} is not a ScientificPolicy")
        return value

    def action(self, action_id: str) -> ActionSpec:
        value = self.get(action_id)
        if not isinstance(value, ActionSpec):
            raise KeyError(f"{action_id!r} is not an ActionSpec")
        return value

    def search_decisions(self, state_id: str) -> tuple[SearchDecision, ...]:
        values = [
            obj
            for obj in self._objects.values()
            if isinstance(obj, SearchDecision) and obj.state_id == state_id
        ]
        return tuple(sorted(values, key=lambda item: item.decision_id))

    def claim_assessments(self, state_id: str) -> tuple[ClaimAssessment, ...]:
        values = [
            obj
            for obj in self._objects.values()
            if isinstance(obj, ClaimAssessment) and obj.state_id == state_id
        ]
        return tuple(sorted(values, key=lambda item: item.assessment_id))

    def transition(self, transition_id: str) -> StateTransition:
        try:
            return self._transitions[transition_id]
        except KeyError as exc:
            raise KeyError(f"unknown StateTransition {transition_id!r}") from exc

    def state_delta(self, transition_id: str) -> StateDelta:
        return self.transition(transition_id).delta

    def repository_only_transitions(self, case_id: str) -> tuple[StateTransition, ...]:
        values = []
        for transition in self.state_transitions(case_id):
            delta = transition.delta
            if (
                delta.repository_delta
                and not delta.world_delta
                and not delta.observation_delta
                and not delta.epistemic_delta
                and not delta.search_delta
                and not delta.claim_delta
            ):
                values.append(transition)
        return tuple(values)

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
        non_leaves = {
            transition.predecessor_id
            for transition in self._transitions.values()
            if self._states[transition.predecessor_id].case_id == case_id
        }
        leaves = [state for state in states if state.state_id not in non_leaves]
        if len(leaves) == 1:
            return leaves[0]
        if len(states) == 1:
            return states[0]
        return sorted(leaves or states, key=lambda item: item.state_id)[-1]

    def proposition_assessment_history(self, proposition_id: str) -> tuple[Any, ...]:
        values = [
            obj
            for obj in self._objects.values()
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
            transition
            for transition in self._transitions.values()
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

    @staticmethod
    def _type_registry() -> dict[str, type[Any]]:
        return {
            name: value
            for name, value in vars(semantic_model).items()
            if isinstance(value, type) and is_dataclass(value)
        }

    @classmethod
    def _coerce_value(cls, annotation: Any, value: Any) -> Any:
        if annotation is Any or annotation is None:
            return value
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin in (Union, types.UnionType):
            if value is None and type(None) in args:
                return None
            for candidate in args:
                if candidate is type(None):
                    continue
                try:
                    return cls._coerce_value(candidate, value)
                except (TypeError, ValueError, KeyError):
                    continue
            return value
        if origin is tuple:
            if not args:
                return tuple(value)
            item_type = args[0]
            if len(args) == 2 and args[1] is Ellipsis:
                return tuple(cls._coerce_value(item_type, item) for item in value)
            return tuple(
                cls._coerce_value(item_annotation, item)
                for item_annotation, item in zip(args, value, strict=True)
            )
        if origin is list:
            item_type = args[0] if args else Any
            return [cls._coerce_value(item_type, item) for item in value]
        if origin is dict:
            key_type, item_type = args or (Any, Any)
            return {
                cls._coerce_value(key_type, key): cls._coerce_value(item_type, item)
                for key, item in value.items()
            }
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return annotation(value)
        if isinstance(annotation, type) and is_dataclass(annotation):
            return cls._deserialize_dataclass(annotation, value)
        return value

    @classmethod
    def _deserialize_dataclass(cls, target_type: type[Any], payload: dict[str, Any]) -> Any:
        hints = get_type_hints(target_type)
        kwargs: dict[str, Any] = {}
        for field in fields(target_type):
            if field.name not in payload:
                continue
            kwargs[field.name] = cls._coerce_value(
                hints.get(field.name, field.type), payload[field.name]
            )
        return target_type(**kwargs)

    @classmethod
    def _deserialize(cls, payload: dict[str, Any]) -> Any:
        type_name = payload.get("__type__")
        if not isinstance(type_name, str):
            raise SemanticInvariantError("persisted semantic object has no __type__")
        target_type = cls._type_registry().get(type_name)
        if target_type is None:
            raise SemanticVersionError(f"unsupported persisted semantic type: {type_name}")
        values = {key: value for key, value in payload.items() if key != "__type__"}
        return cls._deserialize_dataclass(target_type, values)

    def save_json(self, path: str | Path) -> Path:
        target = Path(path)
        payload = {
            "semantic_contract": SEMANTIC_CONTRACT_ID,
            "ontology_schema_version": ONTOLOGY_SCHEMA_VERSION,
            "objects": [self._serialize(obj) for _, obj in sorted(self._objects.items())],
        }
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return target

    @classmethod
    def load_json(cls, path: str | Path) -> "OntologyService":
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("semantic_contract") != SEMANTIC_CONTRACT_ID:
            raise SemanticVersionError(
                f"persisted semantic contract {payload.get('semantic_contract')!r} "
                f"!= {SEMANTIC_CONTRACT_ID!r}"
            )
        if str(payload.get("ontology_schema_version")) != ONTOLOGY_SCHEMA_VERSION:
            raise SemanticVersionError(
                f"persisted ontology schema version {payload.get('ontology_schema_version')!r} "
                f"!= {ONTOLOGY_SCHEMA_VERSION!r}"
            )
        objects = payload.get("objects")
        if not isinstance(objects, list):
            raise SemanticInvariantError("persisted ontology objects must be an array")
        decoded = [cls._deserialize(item) for item in objects]
        service = cls()
        for obj in decoded:
            if isinstance(obj, (DevelopmentState, StateTransition)):
                continue
            service.register(obj)
        for obj in decoded:
            if isinstance(obj, DevelopmentState):
                service.commit_state(obj)
        for obj in decoded:
            if isinstance(obj, StateTransition):
                service.commit_transition(obj)
        return service

    def project_to_owlready(self, *, world: Any | None = None) -> Any:
        """Project registered objects into an explicit Owlready2 World lazily."""
        from .owlready import Owlready2Projection

        projection = Owlready2Projection(world=world)
        projection.materialize(self._objects.values())
        return projection


__all__ = ["OntologyService", "SemanticInvariantError", "SemanticVersionError"]
