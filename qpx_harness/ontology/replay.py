"""Deterministic historical replay queries for QPX_STATE_SEMANTICS_V1.

This module does not invent historical evidence. It evaluates semantic objects
that a fixture has explicitly materialized from issue bodies, persisted summaries,
or other provenance-qualified sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .model import (
    ActionExecution,
    ActionSpec,
    ClaimAssessment,
    DevelopmentState,
    DiagnosticConclusion,
    DerivedFact,
    Evidence,
    EvidenceAvailability,
    ExecutionOutcome,
    HypothesisAssessment,
    OpenQuestion,
    SearchDecision,
)
from .service import OntologyService, SemanticInvariantError


QUERY_IDS = (
    "Q1_CURRENT_STATE",
    "Q2_EPISTEMIC_PARTITION",
    "Q3_HYPOTHESIS_TRAJECTORY",
    "Q4_EVIDENCE_LINEAGE",
    "Q5_SEARCH_HISTORY",
    "Q6_STATE_DELTA",
    "Q7_CLAIM_READINESS",
    "Q8_ABSENCE_SCOPE",
    "Q9_REPOSITORY_ONLY_CHANGE",
)


@dataclass(frozen=True)
class HistoricalReplayFixture:
    fixture_id: str
    source_issues: tuple[int, ...]
    available_sources: tuple[str, ...]
    provenance_quality: str
    initial_state_id: str
    expected_terminal_state_id: str | None
    expected_queries: tuple[tuple[str, Any], ...] = ()
    missing_sources: tuple[str, ...] = ()
    explicitly_unknown: tuple[str, ...] = ()

    def expected_query_map(self) -> dict[str, Any]:
        return dict(self.expected_queries)


@dataclass(frozen=True)
class ReplayAcceptance:
    fixture_id: str
    passed: bool
    query_results: tuple[tuple[str, Any], ...]
    mismatches: tuple[str, ...] = ()

    def result_map(self) -> dict[str, Any]:
        return dict(self.query_results)


def _enum(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _identity(obj: Any) -> str:
    return OntologyService._identity(obj)


def validate_fixture_contract(fixture: HistoricalReplayFixture) -> None:
    if not fixture.fixture_id.strip():
        raise SemanticInvariantError("historical replay fixture_id is required")
    if not fixture.source_issues:
        raise SemanticInvariantError(f"{fixture.fixture_id}: source_issues is empty")
    if not fixture.available_sources:
        raise SemanticInvariantError(f"{fixture.fixture_id}: available_sources is empty")
    if not fixture.provenance_quality.strip():
        raise SemanticInvariantError(f"{fixture.fixture_id}: provenance_quality is required")
    if not fixture.initial_state_id.strip():
        raise SemanticInvariantError(f"{fixture.fixture_id}: initial_state_id is required")
    unknown_queries = set(fixture.expected_query_map()) - set(QUERY_IDS)
    if unknown_queries:
        raise SemanticInvariantError(
            f"{fixture.fixture_id}: unknown replay queries: {sorted(unknown_queries)}"
        )


def _state(service: OntologyService, state_id: str) -> DevelopmentState:
    value = service.get(state_id)
    if not isinstance(value, DevelopmentState):
        raise SemanticInvariantError(f"{state_id!r} is not a DevelopmentState")
    return value


def _current_state(service: OntologyService, case_id: str) -> dict[str, Any] | None:
    state = service.current_state(case_id)
    if state is None:
        return None
    return {
        "state_id": state.state_id,
        "case_id": state.case_id,
        "provenance_id": state.provenance_id,
    }


def _epistemic_partition(service: OntologyService, case_id: str) -> dict[str, Any]:
    state = service.current_state(case_id)
    if state is None:
        return {
            "hypotheses": (),
            "claims": (),
            "diagnostics": (),
            "derived_facts": (),
        }
    hypotheses = []
    for assessment_id in state.hypothesis_assessment_ids:
        item = service.get(assessment_id)
        if not isinstance(item, HypothesisAssessment):
            raise SemanticInvariantError(
                f"{state.state_id}: {assessment_id!r} is not HypothesisAssessment"
            )
        hypotheses.append(
            (
                item.hypothesis_id,
                _enum(item.support),
                _enum(item.resolution),
                _enum(item.scope),
            )
        )
    claims = []
    for assessment_id in state.claim_assessment_ids:
        item = service.get(assessment_id)
        if not isinstance(item, ClaimAssessment):
            raise SemanticInvariantError(
                f"{state.state_id}: {assessment_id!r} is not ClaimAssessment"
            )
        claims.append(
            (
                item.claim_id,
                _enum(item.validation),
                _enum(item.applicability),
                _enum(item.acceptance),
                _enum(item.production_readiness),
            )
        )
    diagnostics = []
    for conclusion_id in state.diagnostic_conclusion_ids:
        item = service.get(conclusion_id)
        if not isinstance(item, DiagnosticConclusion):
            raise SemanticInvariantError(
                f"{state.state_id}: {conclusion_id!r} is not DiagnosticConclusion"
            )
        diagnostics.append(
            (
                item.conclusion_id,
                item.localized_owner,
                item.owner_granularity,
                item.mechanism_id,
            )
        )
    derived = []
    for fact_id in state.derived_fact_ids:
        item = service.get(fact_id)
        if not isinstance(item, DerivedFact):
            raise SemanticInvariantError(
                f"{state.state_id}: {fact_id!r} is not DerivedFact"
            )
        derived.append((item.fact_id, item.statement))
    return {
        "hypotheses": tuple(sorted(hypotheses)),
        "claims": tuple(sorted(claims)),
        "diagnostics": tuple(sorted(diagnostics)),
        "derived_facts": tuple(sorted(derived)),
    }


def _hypothesis_trajectory(service: OntologyService, case_id: str) -> tuple[Any, ...]:
    state_ids = {
        obj.state_id
        for obj in service.objects(DevelopmentState)
        if obj.case_id == case_id
    }
    by_hypothesis: dict[str, list[tuple[Any, ...]]] = {}
    for item in service.objects(HypothesisAssessment):
        if item.state_id not in state_ids:
            continue
        by_hypothesis.setdefault(item.hypothesis_id, []).append(
            (
                item.state_id,
                _enum(item.support),
                _enum(item.resolution),
                _enum(item.scope),
                item.assessment_id,
            )
        )
    return tuple(
        (hypothesis_id, tuple(sorted(history)))
        for hypothesis_id, history in sorted(by_hypothesis.items())
    )


def _evidence_lineage(service: OntologyService, case_id: str) -> tuple[Any, ...]:
    state_ids = {
        obj.state_id
        for obj in service.objects(DevelopmentState)
        if obj.case_id == case_id
    }
    evidence_ids: set[str] = set()
    for state_id in state_ids:
        state = _state(service, state_id)
        evidence_ids.update(state.evidence_ids)
        for assessment_id in (
            *state.hypothesis_assessment_ids,
            *state.claim_assessment_ids,
        ):
            assessment = service.get(assessment_id)
            evidence_ids.update(getattr(assessment, "evidence_ids", ()))
        for conclusion_id in state.diagnostic_conclusion_ids:
            conclusion = service.get(conclusion_id)
            evidence_ids.update(getattr(conclusion, "evidence_ids", ()))

    result = []
    for evidence_id in sorted(evidence_ids):
        evidence = service.get(evidence_id)
        if not isinstance(evidence, Evidence):
            raise SemanticInvariantError(
                f"{case_id}: {evidence_id!r} is not Evidence"
            )
        lineage = tuple(_identity(obj) for obj in service.provenance_chain(evidence_id))
        result.append(
            (
                evidence.evidence_id,
                evidence.observation_id,
                evidence.context_id,
                _enum(evidence.availability),
                _enum(evidence.admissibility),
                lineage,
            )
        )
    return tuple(result)


def _search_history(service: OntologyService, case_id: str) -> dict[str, Any]:
    state_ids = {
        obj.state_id
        for obj in service.objects(DevelopmentState)
        if obj.case_id == case_id
    }
    considered_action_ids: set[str] = set()
    for state_id in state_ids:
        considered_action_ids.update(_state(service, state_id).considered_action_ids)

    actions = []
    for action_id in sorted(considered_action_ids):
        action = service.get(action_id)
        if not isinstance(action, ActionSpec):
            raise SemanticInvariantError(f"{action_id!r} is not ActionSpec")
        actions.append((action.action_id, action.intervention_type, action.target))

    decisions = tuple(
        sorted(
            (
                obj.decision_id,
                obj.state_id,
                obj.action_id,
                obj.disposition,
            )
            for obj in service.objects(SearchDecision)
            if obj.state_id in state_ids
        )
    )
    executions = tuple(
        sorted(
            (
                obj.execution_id,
                obj.source_state_id,
                obj.action_id,
                _enum(obj.status),
            )
            for obj in service.objects(ActionExecution)
            if obj.source_state_id in state_ids
        )
    )
    execution_ids = {item[0] for item in executions}
    outcomes = tuple(
        sorted(
            (
                obj.outcome_id,
                obj.execution_id,
                _enum(obj.status),
            )
            for obj in service.objects(ExecutionOutcome)
            if obj.execution_id in execution_ids
        )
    )
    return {
        "actions": tuple(actions),
        "decisions": decisions,
        "executions": executions,
        "outcomes": outcomes,
    }


def _state_delta(service: OntologyService, case_id: str) -> tuple[Any, ...]:
    result = []
    for transition in service.state_transitions(case_id):
        delta = transition.delta
        result.append(
            (
                transition.transition_id,
                transition.predecessor_id,
                transition.successor_id,
                transition.caused_by_execution_id,
                delta.world_delta,
                delta.observation_delta,
                delta.epistemic_delta,
                delta.search_delta,
                delta.claim_delta,
                delta.repository_delta,
            )
        )
    return tuple(result)


def _claim_readiness(service: OntologyService, case_id: str) -> tuple[Any, ...]:
    state = service.current_state(case_id)
    if state is None:
        return ()
    result = []
    for assessment_id in state.claim_assessment_ids:
        item = service.get(assessment_id)
        if not isinstance(item, ClaimAssessment):
            raise SemanticInvariantError(
                f"{assessment_id!r} is not ClaimAssessment"
            )
        result.append(
            (
                item.claim_id,
                _enum(item.validation),
                _enum(item.applicability),
                _enum(item.acceptance),
                _enum(item.production_readiness),
                item.blocker_ids,
            )
        )
    return tuple(sorted(result))


def _absence_scope(service: OntologyService, case_id: str) -> dict[str, Any]:
    state_ids = {
        obj.state_id
        for obj in service.objects(DevelopmentState)
        if obj.case_id == case_id
    }
    state_evidence_ids = {
        evidence_id
        for state_id in state_ids
        for evidence_id in _state(service, state_id).evidence_ids
    }
    evidence = tuple(
        sorted(
            (
                obj.evidence_id,
                _enum(obj.availability),
                _enum(obj.admissibility),
            )
            for obj in service.objects(Evidence)
            if obj.evidence_id in state_evidence_ids
            and obj.availability is not EvidenceAvailability.AVAILABLE
        )
    )
    hypotheses = tuple(
        sorted(
            (
                obj.hypothesis_id,
                obj.state_id,
                _enum(obj.support),
                _enum(obj.scope),
            )
            for obj in service.objects(HypothesisAssessment)
            if obj.state_id in state_ids and _enum(obj.scope) != "IN_SCOPE"
        )
    )
    questions = tuple(
        sorted(
            (question_id, service.get(question_id).statement)
            for state_id in state_ids
            for question_id in _state(service, state_id).open_question_ids
            if isinstance(service.get(question_id), OpenQuestion)
        )
    )
    return {
        "unavailable_evidence": evidence,
        "scoped_hypotheses": hypotheses,
        "open_questions": questions,
    }


def _repository_only(service: OntologyService, case_id: str) -> tuple[str, ...]:
    return tuple(
        transition.transition_id
        for transition in service.repository_only_transitions(case_id)
    )


def run_replay_queries(
    service: OntologyService,
    *,
    case_id: str,
) -> dict[str, Any]:
    return {
        "Q1_CURRENT_STATE": _current_state(service, case_id),
        "Q2_EPISTEMIC_PARTITION": _epistemic_partition(service, case_id),
        "Q3_HYPOTHESIS_TRAJECTORY": _hypothesis_trajectory(service, case_id),
        "Q4_EVIDENCE_LINEAGE": _evidence_lineage(service, case_id),
        "Q5_SEARCH_HISTORY": _search_history(service, case_id),
        "Q6_STATE_DELTA": _state_delta(service, case_id),
        "Q7_CLAIM_READINESS": _claim_readiness(service, case_id),
        "Q8_ABSENCE_SCOPE": _absence_scope(service, case_id),
        "Q9_REPOSITORY_ONLY_CHANGE": _repository_only(service, case_id),
    }


def evaluate_historical_replay(
    service: OntologyService,
    fixture: HistoricalReplayFixture,
    *,
    case_id: str,
) -> ReplayAcceptance:
    validate_fixture_contract(fixture)
    initial = service.maybe_get(fixture.initial_state_id)
    if not isinstance(initial, DevelopmentState) or initial.case_id != case_id:
        raise SemanticInvariantError(
            f"{fixture.fixture_id}: initial state {fixture.initial_state_id!r} "
            f"is not committed for case {case_id!r}"
        )
    results = run_replay_queries(service, case_id=case_id)
    mismatches: list[str] = []
    terminal = service.current_state(case_id)
    if fixture.expected_terminal_state_id is not None:
        actual_terminal = terminal.state_id if terminal is not None else None
        if actual_terminal != fixture.expected_terminal_state_id:
            mismatches.append(
                "terminal state mismatch: "
                f"{actual_terminal!r} != {fixture.expected_terminal_state_id!r}"
            )
    for query_id, expected in fixture.expected_queries:
        actual = results[query_id]
        if actual != expected:
            mismatches.append(f"{query_id}: {actual!r} != {expected!r}")
    return ReplayAcceptance(
        fixture_id=fixture.fixture_id,
        passed=not mismatches,
        query_results=tuple((query_id, results[query_id]) for query_id in QUERY_IDS),
        mismatches=tuple(mismatches),
    )


def historical_coverage_catalog() -> tuple[HistoricalReplayFixture, ...]:
    """Return the minimum #135 historical corpus as provenance contracts.

    Catalog entries intentionally contain no synthetic semantic state. State
    materialization belongs to replay fixtures/tests that can point to a
    concrete issue body or persisted summary.
    """
    return (
        HistoricalReplayFixture(
            fixture_id="issue18-active-kernel-coverage",
            source_issues=(18,),
            available_sources=("GitHub Issue #18 final body",),
            provenance_quality="ISSUE_BODY_FINAL_SUMMARY",
            initial_state_id="issue18:S0",
            expected_terminal_state_id=None,
            explicitly_unknown=(
                "raw user-local EVR bundle bytes are not embedded in the issue body",
            ),
        ),
        HistoricalReplayFixture(
            fixture_id="issue19-checker-representation",
            source_issues=(19,),
            available_sources=("GitHub Issue #19 final body",),
            provenance_quality="ISSUE_BODY_FINAL_SUMMARY",
            initial_state_id="issue19:S0",
            expected_terminal_state_id=None,
        ),
        HistoricalReplayFixture(
            fixture_id="issue20-environment-jit",
            source_issues=(20,),
            available_sources=("GitHub Issue #20 final body",),
            provenance_quality="ISSUE_BODY_FINAL_SUMMARY",
            initial_state_id="issue20:S0",
            expected_terminal_state_id=None,
        ),
        HistoricalReplayFixture(
            fixture_id="issue23-harness-intervention",
            source_issues=(23,),
            available_sources=("GitHub Issue #23 final body",),
            provenance_quality="ISSUE_BODY_FINAL_SUMMARY",
            initial_state_id="issue23:S0",
            expected_terminal_state_id=None,
        ),
        HistoricalReplayFixture(
            fixture_id="issue31-metric-applicability",
            source_issues=(31,),
            available_sources=("GitHub Issue #31 body and accepted R4 summaries",),
            provenance_quality="ISSUE_BODY_AND_PERSISTED_SUMMARY",
            initial_state_id="issue31:S0",
            expected_terminal_state_id=None,
        ),
        HistoricalReplayFixture(
            fixture_id="issue44-observation-time-identity",
            source_issues=(44,),
            available_sources=("GitHub Issue #44 final body",),
            provenance_quality="ISSUE_BODY_FINAL_SUMMARY",
            initial_state_id="issue44:S0",
            expected_terminal_state_id=None,
        ),
        HistoricalReplayFixture(
            fixture_id="issue45-89-scientific-closure",
            source_issues=(45, 46, 86, 87, 88, 89),
            available_sources=(
                "GitHub Issue #45 final body",
                "persisted Issue45 interpretation summary",
            ),
            provenance_quality="ISSUE_BODY_AND_PERSISTED_SUMMARY",
            initial_state_id="issue45:S0",
            expected_terminal_state_id="issue45:S2",
            missing_sources=(
                "raw runtime evidence may be unavailable independently of persisted summary",
            ),
            explicitly_unknown=(
                "restart causality",
                "automatic scaling as unique root cause",
            ),
        ),
        HistoricalReplayFixture(
            fixture_id="issue91-98-fault-isolation",
            source_issues=(91, 92, 93, 94, 98),
            available_sources=(
                "GitHub Issue #91 final body",
                "Issue #94/#98 remedy summaries",
            ),
            provenance_quality="ISSUE_BODY_AND_ACCEPTANCE_SUMMARY",
            initial_state_id="issue91:S0",
            expected_terminal_state_id="issue91:S2",
            explicitly_unknown=("general MOOSE FV defect is not established",),
        ),
    )


__all__ = [
    "QUERY_IDS",
    "HistoricalReplayFixture",
    "ReplayAcceptance",
    "validate_fixture_contract",
    "run_replay_queries",
    "evaluate_historical_replay",
    "historical_coverage_catalog",
]
