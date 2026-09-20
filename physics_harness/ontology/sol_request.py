"""Compile canonical Physics/SOL semantics into Public Contract 0.2 request DTOs.

This module is a semantic compiler only. It does not own adapter discovery,
registry, transport, process/session lifecycle, validation, or execution.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Mapping, Sequence

from .model_artifact import CanonicalModelArtifactRef
from .quantity import RealizationQuantity

_PUBLIC_CONTRACT = "0.2"
_CANONICAL_REF = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+$")
_STABLE_SYMBOL = re.compile(r"^[A-Za-z0-9._-]+$")
_ALLOWED_RELATIONS = {
    "represented_by", "closed_by", "parameterized_by", "defined_on",
    "discretized_by", "applied_to", "analyzed_by", "solved_by",
    "produces", "observed_by",
}
_ALLOWED_ENTITY_KINDS = {
    "physics_model", "mathematical_model", "constitutive_model",
    "spatial_model", "material_model", "condition_model", "numerical_model",
    "observation_model", "analysis", "solver_configuration",
}


class SolRequestCompilationError(ValueError):
    """Canonical semantics are incomplete or unsafe for SOL realization."""


def _canonical_ref(value: str, field: str) -> str:
    if not isinstance(value, str) or not _CANONICAL_REF.fullmatch(value):
        raise SolRequestCompilationError(f"{field} must be a canonical SOL reference")
    if "moose" in value.casefold():
        raise SolRequestCompilationError(f"{field} must not contain MOOSE-native spelling")
    return value


def _symbol_shape(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or not _STABLE_SYMBOL.fullmatch(value):
        raise SolRequestCompilationError(f"{field} must be a stable SOL symbol")
    return value


def _stable_symbol(value: str, field: str) -> str:
    value = _symbol_shape(value, field)
    if "moose" in value.casefold():
        raise SolRequestCompilationError(f"{field} must not contain MOOSE-native spelling")
    return value


@dataclass(frozen=True)
class CanonicalEntity:
    id: str
    kind: str
    semantic_type: str
    parameters: tuple[RealizationQuantity, ...] = ()


@dataclass(frozen=True)
class CanonicalScope:
    id: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalRelation:
    kind: str
    source: str
    target: str


@dataclass(frozen=True)
class CanonicalActionBinding:
    action_id: str
    entity_ids: tuple[str, ...]
    scope_ids: tuple[str, ...]
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalRealizationModel:
    artifact: CanonicalModelArtifactRef
    ontology_version: str
    entities: tuple[CanonicalEntity, ...]
    scopes: tuple[CanonicalScope, ...]
    relations: tuple[CanonicalRelation, ...]
    action_bindings: tuple[CanonicalActionBinding, ...]


@dataclass(frozen=True)
class SolRequest:
    backend_target: Mapping[str, object]
    mapping_plan: Mapping[str, object]
    realization_spec: Mapping[str, object]


class SolRequestCompiler:
    """Compile reviewed canonical owners; never infer semantics from action spelling."""

    def __init__(self, capability_map: Mapping[str, str], *, backend_target: str) -> None:
        self._capability_map = dict(capability_map)
        self._backend_target = _symbol_shape(backend_target, "backend target")

    def compile(
        self,
        model: CanonicalRealizationModel,
        *,
        physics_capabilities: Sequence[str],
    ) -> SolRequest:
        required_capabilities: list[str] = []
        for capability in physics_capabilities:
            try:
                mapped = self._capability_map[capability]
            except KeyError as exc:
                raise SolRequestCompilationError(
                    f"unsupported Physics capability mapping: {capability!r}"
                ) from exc
            required_capabilities.append(_stable_symbol(mapped, "SOL capability"))

        source_model = _canonical_ref(model.artifact.model_id, "source model")
        if model.artifact.public_contract != _PUBLIC_CONTRACT:
            raise SolRequestCompilationError("model artifact public contract must be 0.2")
        if not model.ontology_version:
            raise SolRequestCompilationError("ontology version is required")
        if not model.entities or not model.scopes or not model.relations:
            raise SolRequestCompilationError("canonical entity/relation/scope graph is required")
        if not model.action_bindings:
            raise SolRequestCompilationError("canonical action bindings are required")

        entity_ids = {_canonical_ref(entity.id, "entity id") for entity in model.entities}
        scope_ids = {_canonical_ref(scope.id, "scope id") for scope in model.scopes}
        if len(entity_ids) != len(model.entities):
            raise SolRequestCompilationError("duplicate entity id")
        if len(scope_ids) != len(model.scopes):
            raise SolRequestCompilationError("duplicate scope id")
        entities: list[dict[str, object]] = []
        for entity in model.entities:
            if entity.kind not in _ALLOWED_ENTITY_KINDS:
                raise SolRequestCompilationError(f"unsupported entity kind: {entity.kind!r}")
            _stable_symbol(entity.semantic_type, "semantic type")
            parameters: list[dict[str, object]] = []
            for quantity in entity.parameters:
                semantic_parameter = _canonical_ref(quantity.spec.quantity_id, "semantic parameter")
                unit = _canonical_ref(quantity.spec.unit, "quantity unit")
                if (
                    not isinstance(quantity.value, (int, float))
                    or isinstance(quantity.value, bool)
                    or not math.isfinite(quantity.value)
                ):
                    raise SolRequestCompilationError("realization quantity value must be finite numeric")
                parameters.append({
                    "semantic_parameter": semantic_parameter,
                    "quantity": {"value": quantity.value, "unit": unit},
                })
            item: dict[str, object] = {
                "id": entity.id, "kind": entity.kind, "semantic_type": entity.semantic_type
            }
            if parameters:
                item["parameters"] = parameters
            entities.append(item)

        scopes: list[dict[str, object]] = []
        for scope in model.scopes:
            _canonical_ref(scope.id, "scope id")
            if not scope.members:
                raise SolRequestCompilationError("scope members are required")
            for member in scope.members:
                if _canonical_ref(member, "scope member") not in entity_ids:
                    raise SolRequestCompilationError(f"scope references unknown entity: {member!r}")
            scopes.append({"id": scope.id, "members": list(scope.members)})

        relations: list[dict[str, str]] = []
        for relation in model.relations:
            if relation.kind not in _ALLOWED_RELATIONS:
                raise SolRequestCompilationError(f"unsupported relation kind: {relation.kind!r}")
            if _canonical_ref(relation.source, "relation source") not in entity_ids:
                raise SolRequestCompilationError("relation source is not a canonical entity")
            if _canonical_ref(relation.target, "relation target") not in entity_ids:
                raise SolRequestCompilationError("relation target is not a canonical entity")
            relations.append({"kind": relation.kind, "source": relation.source, "target": relation.target})

        action_ids = {_symbol_shape(binding.action_id, "action id") for binding in model.action_bindings}
        if len(action_ids) != len(model.action_bindings):
            raise SolRequestCompilationError("duplicate action id")
        actions: list[dict[str, object]] = []
        bindings: list[dict[str, object]] = []
        for binding in model.action_bindings:
            for dependency in binding.dependencies:
                if _symbol_shape(dependency, "action dependency") not in action_ids:
                    raise SolRequestCompilationError("action dependency references unknown action")
            subjects = []
            for entity_id in binding.entity_ids:
                if _canonical_ref(entity_id, "binding entity") not in entity_ids:
                    raise SolRequestCompilationError("action binding references unknown entity")
                subjects.append({"subject_kind": "entity", "id": entity_id})
            for scope_id in binding.scope_ids:
                if _canonical_ref(scope_id, "binding scope") not in scope_ids:
                    raise SolRequestCompilationError("action binding references unknown scope")
            if not subjects and not binding.scope_ids:
                raise SolRequestCompilationError("action binding requires a canonical subject or scope")
            actions.append({"id": binding.action_id, "dependencies": list(binding.dependencies)})
            item: dict[str, object] = {"action_id": binding.action_id}
            if subjects:
                item["subjects"] = subjects
            if binding.scope_ids:
                item["scopes"] = list(binding.scope_ids)
            bindings.append(item)

        return SolRequest(
            backend_target={
                "public_contract_version": _PUBLIC_CONTRACT,
                "target": self._backend_target,
                "required_capabilities": required_capabilities,
            },
            mapping_plan={"public_contract_version": _PUBLIC_CONTRACT, "actions": actions},
            realization_spec={
                "public_contract_version": _PUBLIC_CONTRACT,
                "ontology_version": model.ontology_version,
                "source_model": source_model,
                "entities": entities,
                "scopes": scopes,
                "relations": relations,
                "action_bindings": bindings,
            },
        )


__all__ = [
    "CanonicalActionBinding", "CanonicalEntity", "CanonicalRealizationModel",
    "CanonicalRelation", "CanonicalScope", "SolRequest", "SolRequestCompilationError",
    "SolRequestCompiler",
]
