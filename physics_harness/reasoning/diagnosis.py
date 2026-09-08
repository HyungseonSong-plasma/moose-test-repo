"""Generic state-scoped diagnosis representation."""
from __future__ import annotations

from dataclasses import dataclass

from qpx_harness.ontology.records import DiagnosticConclusion


@dataclass(frozen=True)
class FailureLocation:
    entity_kind: str
    metric: str
    elem_id: int
    centroid: tuple[float, float]
    error_value: float
    face_id: int | None = None
    run_id: str | None = None
    case_id: str | None = None


@dataclass(frozen=True)
class ReasoningDecision:
    solver_status: str
    status: str
    primary_owner_class: str | None = None
    selected_rule_id: str | None = None
    backend_model: str | None = None


@dataclass(frozen=True)
class DiagnosisReport:
    status: str
    metrics: tuple[tuple[str, float], ...]
    primary_owner_class: str | None = None
    selected_rule_id: str | None = None
    failing_locations: tuple[FailureLocation, ...] = ()
    decision_order: tuple[str, ...] = ()
    solver_status: str | None = None
    backend_model: str | None = None

    def to_conclusion(self, *, conclusion_id: str, state_id: str) -> DiagnosticConclusion:
        return DiagnosticConclusion(
            conclusion_id=conclusion_id,
            state_id=state_id,
            statement=self.status,
            localized_owner=self.primary_owner_class,
            owner_granularity="OWNER_CLASS" if self.primary_owner_class else None,
        )


__all__ = ["DiagnosticConclusion", "DiagnosisReport", "FailureLocation", "ReasoningDecision"]
