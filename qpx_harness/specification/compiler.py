"""Deterministic ExperimentSpec -> ExperimentIntent semantic compiler."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable

from qpx_harness.ontology.model import (
    CapabilityDescriptor,
    Constraint,
    DevelopmentGoal,
    ExperimentIntent,
    ProvenanceRecord,
    SEMANTIC_CONTRACT_ID,
)
from qpx_harness.ontology.service import OntologyService

from .schema import ExperimentSpec, UnsupportedCapabilityError


@dataclass(frozen=True)
class SemanticCompilation:
    source_spec_identity: str
    intent: ExperimentIntent
    goals: tuple[DevelopmentGoal, ...]
    constraints: tuple[Constraint, ...]
    unresolved_capabilities: tuple[str, ...]
    provenance: ProvenanceRecord
    semantic_contract: str = SEMANTIC_CONTRACT_ID


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_experiment_intent(
    spec: ExperimentSpec,
    *,
    capabilities: Iterable[CapabilityDescriptor] = (),
    ontology: OntologyService | None = None,
    allow_unresolved_capabilities: bool = False,
) -> SemanticCompilation:
    capability_map = {item.capability_id: item for item in capabilities}
    unresolved = tuple(
        item
        for item in spec.requested_capabilities
        if item not in capability_map or not capability_map[item].available
    )
    if unresolved and not allow_unresolved_capabilities:
        raise UnsupportedCapabilityError(
            "unsupported semantic capability: " + ", ".join(unresolved)
        )

    source_hash = _file_hash(spec.source_path) if spec.source_path.exists() else "unavailable"
    provenance_id = f"prov:spec:{spec.experiment_id}:{source_hash[:16]}"
    provenance = ProvenanceRecord(
        provenance_id=provenance_id,
        source_identity=str(spec.source_path),
        metadata=(
            ("schema_version", str(spec.schema_version)),
            ("semantic_contract", SEMANTIC_CONTRACT_ID),
            ("source_hash", source_hash),
            ("compiler", "qpx_harness.specification.compiler:v1"),
        ),
    )

    goals = tuple(
        DevelopmentGoal(
            goal_id=f"goal:{spec.experiment_id}:{index}",
            statement=statement,
        )
        for index, statement in enumerate(spec.target_claims + spec.target_questions or (spec.objective,))
    )
    constraints = tuple(
        Constraint(
            constraint_id=f"constraint:{spec.experiment_id}:{index}",
            statement=statement,
        )
        for index, statement in enumerate(spec.constraints)
    )
    intent = ExperimentIntent(
        intent_id=f"intent:{spec.experiment_id}:{source_hash[:16]}",
        experiment_id=spec.experiment_id,
        objective=spec.objective,
        goal_ids=tuple(item.goal_id for item in goals),
        target_ids=tuple(item.goal_id for item in goals),
        requested_capabilities=spec.requested_capabilities,
        parameters=spec.parameters,
        constraint_ids=tuple(item.constraint_id for item in constraints),
        requested_observations=spec.observations,
        execution_bounds=spec.execution_bounds,
        provenance_id=provenance_id,
    )

    result = SemanticCompilation(
        source_spec_identity=str(spec.source_path),
        intent=intent,
        goals=goals,
        constraints=constraints,
        unresolved_capabilities=unresolved,
        provenance=provenance,
    )
    if ontology is not None:
        ontology.register_many((provenance, *goals, *constraints, intent))
    return result


__all__ = ["SemanticCompilation", "compile_experiment_intent"]
