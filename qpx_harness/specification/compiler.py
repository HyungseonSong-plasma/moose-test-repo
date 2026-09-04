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
    ExperimentCaseIntent,
    ExperimentIntent,
    OpenQuestion,
    ProvenanceRecord,
    SEMANTIC_CONTRACT_ID,
    ValidationClaim,
)
from qpx_harness.ontology.service import OntologyService

from .schema import ExperimentSpec, UnsupportedCapabilityError

COMPILER_ID = "qpx_harness.specification.compiler:v2"


@dataclass(frozen=True)
class SemanticCompilation:
    source_spec_identity: str
    intent: ExperimentIntent
    goals: tuple[DevelopmentGoal, ...]
    target_claims: tuple[ValidationClaim, ...]
    target_questions: tuple[OpenQuestion, ...]
    constraints: tuple[Constraint, ...]
    cases: tuple[ExperimentCaseIntent, ...]
    unresolved_capabilities: tuple[str, ...]
    provenance: ProvenanceRecord
    semantic_contract: str = SEMANTIC_CONTRACT_ID

    @property
    def target_ids(self) -> tuple[str, ...]:
        return self.intent.target_ids


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_suffix(kind: str, statement: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{statement}".encode("utf-8")).hexdigest()
    return digest[:16]


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
    metadata = {
        "compiler": COMPILER_ID,
        "experiment_id": spec.experiment_id,
        "schema_version": str(spec.schema_version),
        "semantic_contract": SEMANTIC_CONTRACT_ID,
        "source_hash": source_hash,
        **dict(spec.provenance),
    }
    provenance = ProvenanceRecord(
        provenance_id=provenance_id,
        source_identity=str(spec.source_path),
        metadata=tuple(sorted((str(key), str(value)) for key, value in metadata.items())),
    )

    goals = (
        DevelopmentGoal(
            goal_id=f"goal:{spec.experiment_id}:objective",
            statement=spec.objective,
        ),
    )
    target_claims = tuple(
        ValidationClaim(
            proposition_id=(
                f"claim:{spec.experiment_id}:"
                f"{_stable_suffix('claim', statement)}"
            ),
            statement=statement,
        )
        for statement in spec.target_claims
    )
    target_questions = tuple(
        OpenQuestion(
            question_id=(
                f"question:{spec.experiment_id}:"
                f"{_stable_suffix('question', statement)}"
            ),
            statement=statement,
        )
        for statement in spec.target_questions
    )
    constraints = tuple(
        Constraint(
            constraint_id=(
                f"constraint:{spec.experiment_id}:"
                f"{_stable_suffix('constraint', statement)}"
            ),
            statement=statement,
        )
        for statement in spec.constraints
    )
    constraint_ids_by_statement = {
        item.statement: item.constraint_id for item in constraints
    }

    case_constraints: list[Constraint] = []
    cases: list[ExperimentCaseIntent] = []
    for case in spec.cases:
        ids: list[str] = []
        for statement in case.constraints:
            constraint_id = constraint_ids_by_statement.get(statement)
            if constraint_id is None:
                constraint_id = (
                    f"constraint:{spec.experiment_id}:case:{case.case_id}:"
                    f"{_stable_suffix('case-constraint', statement)}"
                )
                case_constraints.append(
                    Constraint(
                        constraint_id=constraint_id,
                        statement=statement,
                        kind="CASE_DECLARATION",
                    )
                )
            ids.append(constraint_id)
        cases.append(
            ExperimentCaseIntent(
                case_id=f"case:{spec.experiment_id}:{case.case_id}",
                parameters=case.parameters,
                constraint_ids=tuple(ids),
            )
        )
    constraints = (*constraints, *tuple(case_constraints))

    target_ids = (
        *(item.proposition_id for item in target_claims),
        *(item.question_id for item in target_questions),
    )
    intent = ExperimentIntent(
        intent_id=f"intent:{spec.experiment_id}:{source_hash[:16]}",
        experiment_id=spec.experiment_id,
        objective=spec.objective,
        model=spec.model,
        goal_ids=tuple(item.goal_id for item in goals),
        target_ids=tuple(target_ids),
        requested_capabilities=spec.requested_capabilities,
        parameters=spec.parameters,
        constraint_ids=tuple(
            item.constraint_id for item in constraints if item.kind == "DECLARED"
        ),
        requested_observations=spec.observations,
        execution_bounds=spec.execution_bounds,
        case_ids=tuple(item.case_id for item in cases),
        provenance_id=provenance_id,
    )

    result = SemanticCompilation(
        source_spec_identity=str(spec.source_path),
        intent=intent,
        goals=goals,
        target_claims=target_claims,
        target_questions=target_questions,
        constraints=tuple(constraints),
        cases=tuple(cases),
        unresolved_capabilities=unresolved,
        provenance=provenance,
    )
    if ontology is not None:
        ontology.register_many(
            (
                provenance,
                *goals,
                *target_claims,
                *target_questions,
                *constraints,
                *cases,
                intent,
            )
        )
    return result


__all__ = ["COMPILER_ID", "SemanticCompilation", "compile_experiment_intent"]
