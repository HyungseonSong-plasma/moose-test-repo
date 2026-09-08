"""Optional Owlready2 projection for the Physics semantic model.

The module deliberately imports Owlready2 lazily so architecture tests do not
require a JVM or reasoner. When used, every projection owns an explicit World;
`default_world` is never semantic authority.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import re
import types
from typing import Any, Iterable

from .records import ONTOLOGY_SCHEMA_VERSION, SEMANTIC_CONTRACT_ID

ONTOLOGY_IRI = "https://physics.local/ontology/development-state/v1#"


class Owlready2Unavailable(RuntimeError):
    pass


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not value or value[0].isdigit():
        value = f"id_{value}"
    return value


class Owlready2Projection:
    """Materialize semantic records into one isolated Owlready2 World."""

    def __init__(self, *, world: Any | None = None) -> None:
        try:
            import owlready2 as owl
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise Owlready2Unavailable(
                "Owlready2 projection requested but the 'owlready2' package is not installed"
            ) from exc
        self.owl = owl
        self.world = world if world is not None else owl.World()
        self.onto = self.world.get_ontology(ONTOLOGY_IRI)
        self._classes: dict[str, Any] = {}
        self._build_schema()

    def _build_schema(self) -> None:
        owl = self.owl
        with self.onto:
            class SemanticEntity(owl.Thing):
                pass

            class semantic_id(owl.DataProperty, owl.FunctionalProperty):
                domain = [SemanticEntity]
                range = [str]

            class semantic_type(owl.DataProperty, owl.FunctionalProperty):
                domain = [SemanticEntity]
                range = [str]

            class semantic_contract(owl.DataProperty, owl.FunctionalProperty):
                domain = [SemanticEntity]
                range = [str]

            class schema_version(owl.DataProperty, owl.FunctionalProperty):
                domain = [SemanticEntity]
                range = [str]

            class references(owl.ObjectProperty):
                domain = [SemanticEntity]
                range = [SemanticEntity]

            class predecessor(owl.ObjectProperty, owl.FunctionalProperty):
                domain = [SemanticEntity]
                range = [SemanticEntity]

            class successor(owl.ObjectProperty, owl.FunctionalProperty):
                domain = [SemanticEntity]
                range = [SemanticEntity]

            class caused_by(owl.ObjectProperty):
                domain = [SemanticEntity]
                range = [SemanticEntity]

            class assessed_in(owl.ObjectProperty, owl.FunctionalProperty):
                domain = [SemanticEntity]
                range = [SemanticEntity]

            class has_provenance(owl.ObjectProperty):
                domain = [SemanticEntity]
                range = [SemanticEntity]

        self.SemanticEntity = self.onto.SemanticEntity
        self.semantic_id = self.onto.semantic_id
        self.semantic_type = self.onto.semantic_type
        self.semantic_contract = self.onto.semantic_contract
        self.schema_version = self.onto.schema_version
        self.references = self.onto.references
        self.predecessor = self.onto.predecessor
        self.successor = self.onto.successor
        self.caused_by = self.onto.caused_by
        self.assessed_in = self.onto.assessed_in
        self.has_provenance = self.onto.has_provenance

    @staticmethod
    def _identity(obj: Any) -> str:
        for name in (
            "state_id", "intent_id", "goal_id", "capability_id", "artifact_id",
            "observation_id", "evidence_id", "fact_id", "proposition_id",
            "question_id", "case_id", "assessment_id", "conclusion_id",
            "action_id", "decision_id", "policy_id", "execution_id", "outcome_id",
            "transition_id", "provenance_id", "constraint_id",
        ):
            value = getattr(obj, name, None)
            if value:
                return str(value)
        raise ValueError(f"cannot project object without stable identity: {type(obj).__name__}")

    def _semantic_class(self, type_name: str) -> Any:
        existing = self._classes.get(type_name)
        if existing is not None:
            return existing
        existing = getattr(self.onto, type_name, None)
        if existing is not None:
            self._classes[type_name] = existing
            return existing
        with self.onto:
            cls = types.new_class(type_name, (self.SemanticEntity,))
        self._classes[type_name] = cls
        return cls

    def _individual(self, identity: str) -> Any:
        return self.world[f"{ONTOLOGY_IRI}{_safe_name(identity)}"]

    def individual(self, identity: str) -> Any:
        """Return a projected semantic individual by stable identity, read only."""
        return self._individual(identity)

    def materialize(self, objects: Iterable[Any]) -> None:
        objects = tuple(objects)
        by_id = {self._identity(obj): obj for obj in objects}

        for identity, obj in by_id.items():
            cls = self._semantic_class(type(obj).__name__)
            individual = self._individual(identity)
            if individual is None:
                individual = cls(_safe_name(identity), namespace=self.onto)
            individual.semantic_id = identity
            individual.semantic_type = type(obj).__name__
            individual.semantic_contract = SEMANTIC_CONTRACT_ID
            individual.schema_version = ONTOLOGY_SCHEMA_VERSION

        # Second pass links stable semantic references without encoding dense payloads.
        for identity, obj in by_id.items():
            individual = self._individual(identity)
            if individual is None or not is_dataclass(obj):
                continue
            payload = asdict(obj)
            for field_name, value in payload.items():
                if field_name.endswith("_id") and isinstance(value, str) and value in by_id:
                    target = self._individual(value)
                    if target is not None and target not in individual.references:
                        individual.references.append(target)
                elif field_name.endswith("_ids") and isinstance(value, (list, tuple)):
                    for item in value:
                        if isinstance(item, str) and item in by_id:
                            target = self._individual(item)
                            if target is not None and target not in individual.references:
                                individual.references.append(target)

            provenance_id = getattr(obj, "provenance_id", None)
            if provenance_id in by_id:
                target = self._individual(provenance_id)
                if target is not None and target not in individual.has_provenance:
                    individual.has_provenance.append(target)

            state_id = getattr(obj, "state_id", None)
            if state_id in by_id and type(obj).__name__.endswith(("Assessment", "Conclusion")):
                target = self._individual(state_id)
                if target is not None:
                    individual.assessed_in = target

            predecessor_id = getattr(obj, "predecessor_id", None)
            successor_id = getattr(obj, "successor_id", None)
            execution_id = getattr(obj, "caused_by_execution_id", None)
            if predecessor_id in by_id:
                individual.predecessor = self._individual(predecessor_id)
            if successor_id in by_id:
                individual.successor = self._individual(successor_id)
            if execution_id in by_id:
                target = self._individual(execution_id)
                if target not in individual.caused_by:
                    individual.caused_by.append(target)

    def save(self, path: str) -> None:
        self.onto.save(file=path, format="rdfxml")


__all__ = ["ONTOLOGY_IRI", "Owlready2Projection", "Owlready2Unavailable"]
