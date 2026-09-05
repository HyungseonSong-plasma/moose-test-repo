from __future__ import annotations

from pathlib import Path

from qpx_harness.ontology import OntologyService
from qpx_harness.ontology.model import (
    AcceptanceStatus,
    ActionExecution,
    ActionSpec,
    ApplicabilityStatus,
    Artifact,
    ClaimAssessment,
    DevelopmentState,
    DerivedFact,
    DiagnosticConclusion,
    Evidence,
    EvidenceAdmissibility,
    EvidenceAvailability,
    ExecutionOutcome,
    ExecutionOutcomeStatus,
    ExecutionStatus,
    Hypothesis,
    HypothesisAssessment,
    HypothesisSupport,
    OpenQuestion,
    ProductionReadiness,
    ProvenanceRecord,
    ResolutionStatus,
    ScopeStatus,
    SearchDecision,
    StateDelta,
    StateTransition,
    ValidationClaim,
    ValidationStatus,
    Observation,
)
from qpx_harness.ontology.replay import (
    QUERY_IDS,
    HistoricalReplayFixture,
    evaluate_historical_replay,
    historical_coverage_catalog,
    run_replay_queries,
    validate_fixture_contract,
)


ROOT = Path(__file__).resolve().parents[2]


def _register(service: OntologyService, *objects) -> None:
    service.register_many(objects)


def _build_issue45_chain() -> tuple[OntologyService, HistoricalReplayFixture]:
    service = OntologyService()
    artifact = Artifact(
        artifact_id="issue45:body",
        uri="https://github.com/HyungseonSong-plasma/moose-test-repo/issues/45",
        media_type="text/markdown",
        schema_id="github-issue-body",
        provenance_id="issue45:prov",
    )
    provenance = ProvenanceRecord(
        provenance_id="issue45:prov",
        source_identity="GitHub Issue #45 final body",
        artifact_ids=(artifact.artifact_id,),
        metadata=(("quality", "ISSUE_BODY_FINAL_SUMMARY"),),
    )
    conditioning = Observation(
        observation_id="issue45:conditioning-proxy",
        name="conditioning_proxy",
        value=4.200641331042e16,
        artifact_id=artifact.artifact_id,
        provenance_id=provenance.provenance_id,
    )
    runtime_availability = Observation(
        observation_id="issue45:raw-runtime-availability",
        name="raw_runtime_evidence_embedded_in_issue_body",
        value=False,
        artifact_id=artifact.artifact_id,
        provenance_id=provenance.provenance_id,
    )
    e_conditioning = Evidence(
        evidence_id="issue45:evidence-conditioning",
        observation_id=conditioning.observation_id,
        context_id="issue45:conditioning-hypothesis",
        availability=EvidenceAvailability.AVAILABLE,
        admissibility=EvidenceAdmissibility.ADMISSIBLE,
        provenance_id=provenance.provenance_id,
    )
    e_raw = Evidence(
        evidence_id="issue45:evidence-raw-runtime",
        observation_id=runtime_availability.observation_id,
        context_id="issue45:runtime-provenance",
        availability=EvidenceAvailability.UNAVAILABLE,
        admissibility=EvidenceAdmissibility.UNKNOWN,
        provenance_id=provenance.provenance_id,
    )
    closure = DerivedFact(
        fact_id="issue45:fact-physical-closure",
        statement="physical inventory closure is valid for the scoped closed/source-free model",
        source_ids=(e_conditioning.evidence_id,),
        provenance_id=provenance.provenance_id,
    )
    h_conditioning = Hypothesis(
        proposition_id="issue45:H1",
        statement="severe conditioning dominates the augmented saddle-point breakdown",
    )
    h_residual = Hypothesis(
        proposition_id="issue45:H2",
        statement="severe Krylov residual-fidelity loss is the primary breakdown mechanism",
    )
    h_formulation = Hypothesis(
        proposition_id="issue45:H3",
        statement="a structural formulation defect causes the breakdown",
    )
    scientific_claim = ValidationClaim(
        proposition_id="issue45:claim-scientific-closure",
        statement="physical closure is scientifically established for the scoped model",
    )
    restart_question = OpenQuestion(
        question_id="issue45:q-restart-causality",
        statement="is GMRES restart=30 causal rather than merely chronological?",
    )
    action = ActionSpec(
        action_id="issue45:action-evr3",
        intended_effect="increase observability without changing scientific physics",
        target="preconditioned_augmented_saddle_point",
        intervention_type="OBSERVABILITY_ONLY",
        discriminates=(h_conditioning.proposition_id, h_residual.proposition_id),
        preserves=("physical formulation", "accepted Jacobian"),
    )
    decision = SearchDecision(
        decision_id="issue45:decision-evr3",
        state_id="issue45:S0",
        action_id=action.action_id,
        disposition="SELECTED",
        rationale="bounded final discriminator within EVR budget",
    )
    a0_h1 = HypothesisAssessment(
        assessment_id="issue45:A0-H1",
        hypothesis_id=h_conditioning.proposition_id,
        state_id="issue45:S0",
        support=HypothesisSupport.PLAUSIBLE,
    )
    a0_h2 = HypothesisAssessment(
        assessment_id="issue45:A0-H2",
        hypothesis_id=h_residual.proposition_id,
        state_id="issue45:S0",
        support=HypothesisSupport.PLAUSIBLE,
    )
    a0_h3 = HypothesisAssessment(
        assessment_id="issue45:A0-H3",
        hypothesis_id=h_formulation.proposition_id,
        state_id="issue45:S0",
        support=HypothesisSupport.DISFAVORED,
    )
    c0 = ClaimAssessment(
        assessment_id="issue45:C0",
        claim_id=scientific_claim.proposition_id,
        state_id="issue45:S0",
        validation=ValidationStatus.UNASSESSED,
        acceptance=AcceptanceStatus.BLOCKED,
        production_readiness=ProductionReadiness.BLOCKED,
    )
    s0 = DevelopmentState(
        state_id="issue45:S0",
        case_id="issue45",
        evidence_ids=(e_raw.evidence_id,),
        derived_fact_ids=(closure.fact_id,),
        hypothesis_assessment_ids=(a0_h1.assessment_id, a0_h2.assessment_id, a0_h3.assessment_id),
        claim_assessment_ids=(c0.assessment_id,),
        open_question_ids=(restart_question.question_id,),
        considered_action_ids=(action.action_id,),
        provenance_id=provenance.provenance_id,
    )
    execution = ActionExecution(
        execution_id="issue45:execution-evr3",
        action_id=action.action_id,
        source_state_id=s0.state_id,
        status=ExecutionStatus.RUNNING,
        provenance_id=provenance.provenance_id,
    )
    outcome = ExecutionOutcome(
        outcome_id="issue45:outcome-evr3",
        execution_id=execution.execution_id,
        status=ExecutionOutcomeStatus.SUCCEEDED,
        observation_ids=(conditioning.observation_id,),
        message="observability completed; scientific acceptance remains a separate assessment",
    )
    a1_h1 = HypothesisAssessment(
        assessment_id="issue45:A1-H1",
        hypothesis_id=h_conditioning.proposition_id,
        state_id="issue45:S1",
        support=HypothesisSupport.STRONGLY_SUPPORTED,
        resolution=ResolutionStatus.RESOLVED,
        evidence_ids=(e_conditioning.evidence_id,),
    )
    a1_h2 = HypothesisAssessment(
        assessment_id="issue45:A1-H2",
        hypothesis_id=h_residual.proposition_id,
        state_id="issue45:S1",
        support=HypothesisSupport.DISFAVORED,
        resolution=ResolutionStatus.RESOLVED,
        evidence_ids=(e_conditioning.evidence_id,),
    )
    a1_h3 = HypothesisAssessment(
        assessment_id="issue45:A1-H3",
        hypothesis_id=h_formulation.proposition_id,
        state_id="issue45:S1",
        support=HypothesisSupport.DISFAVORED,
        resolution=ResolutionStatus.RESOLVED,
    )
    c1 = ClaimAssessment(
        assessment_id="issue45:C1",
        claim_id=scientific_claim.proposition_id,
        state_id="issue45:S1",
        validation=ValidationStatus.VALIDATED,
        applicability=ApplicabilityStatus.APPLICABLE,
        acceptance=AcceptanceStatus.ACCEPTED,
        production_readiness=ProductionReadiness.BLOCKED,
        evidence_ids=(e_conditioning.evidence_id,),
        blocker_ids=("SEVERE_CONDITIONING_OF_PRECONDITIONED_AUGMENTED_SADDLE_POINT_SYSTEM",),
        provenance_id=provenance.provenance_id,
    )
    d1 = DiagnosticConclusion(
        conclusion_id="issue45:D1",
        state_id="issue45:S1",
        statement="severe conditioning is the numerical blocker; restart causality is not established",
        proposition_ids=(h_conditioning.proposition_id, h_residual.proposition_id, h_formulation.proposition_id),
        evidence_ids=(e_conditioning.evidence_id,),
        localized_owner="preconditioned augmented saddle-point system",
        owner_granularity="OWNER_CLASS",
        mechanism_id=None,
        provenance_id=provenance.provenance_id,
    )
    s1 = DevelopmentState(
        state_id="issue45:S1",
        case_id="issue45",
        observation_ids=(conditioning.observation_id,),
        evidence_ids=(e_conditioning.evidence_id, e_raw.evidence_id),
        derived_fact_ids=(closure.fact_id,),
        hypothesis_assessment_ids=(a1_h1.assessment_id, a1_h2.assessment_id, a1_h3.assessment_id),
        claim_assessment_ids=(c1.assessment_id,),
        diagnostic_conclusion_ids=(d1.conclusion_id,),
        open_question_ids=(restart_question.question_id,),
        considered_action_ids=(action.action_id,),
        provenance_id=provenance.provenance_id,
    )
    t1 = StateTransition(
        transition_id="issue45:T1",
        predecessor_id=s0.state_id,
        successor_id=s1.state_id,
        caused_by_execution_id=execution.execution_id,
        delta=StateDelta(
            observation_delta=(conditioning.observation_id,),
            epistemic_delta=(a1_h1.assessment_id, a1_h2.assessment_id, a1_h3.assessment_id, d1.conclusion_id),
            search_delta=(decision.decision_id, execution.execution_id, outcome.outcome_id),
            claim_delta=(c1.assessment_id,),
        ),
        provenance_id=provenance.provenance_id,
    )

    a2_h1 = HypothesisAssessment(
        assessment_id="issue45:A2-H1",
        hypothesis_id=h_conditioning.proposition_id,
        state_id="issue45:S2",
        support=a1_h1.support,
        resolution=a1_h1.resolution,
        scope=a1_h1.scope,
        evidence_ids=a1_h1.evidence_ids,
    )
    a2_h2 = HypothesisAssessment(
        assessment_id="issue45:A2-H2",
        hypothesis_id=h_residual.proposition_id,
        state_id="issue45:S2",
        support=a1_h2.support,
        resolution=a1_h2.resolution,
        scope=a1_h2.scope,
        evidence_ids=a1_h2.evidence_ids,
    )
    a2_h3 = HypothesisAssessment(
        assessment_id="issue45:A2-H3",
        hypothesis_id=h_formulation.proposition_id,
        state_id="issue45:S2",
        support=a1_h3.support,
        resolution=a1_h3.resolution,
        scope=a1_h3.scope,
    )
    c2 = ClaimAssessment(
        assessment_id="issue45:C2",
        claim_id=scientific_claim.proposition_id,
        state_id="issue45:S2",
        validation=c1.validation,
        applicability=c1.applicability,
        acceptance=c1.acceptance,
        production_readiness=c1.production_readiness,
        evidence_ids=c1.evidence_ids,
        blocker_ids=c1.blocker_ids,
        provenance_id=provenance.provenance_id,
    )
    d2 = DiagnosticConclusion(
        conclusion_id="issue45:D2",
        state_id="issue45:S2",
        statement=d1.statement,
        proposition_ids=d1.proposition_ids,
        evidence_ids=d1.evidence_ids,
        localized_owner=d1.localized_owner,
        owner_granularity=d1.owner_granularity,
        mechanism_id=d1.mechanism_id,
        provenance_id=provenance.provenance_id,
    )
    s2 = DevelopmentState(
        state_id="issue45:S2",
        case_id="issue45",
        observation_ids=s1.observation_ids,
        evidence_ids=s1.evidence_ids,
        derived_fact_ids=s1.derived_fact_ids,
        hypothesis_assessment_ids=(a2_h1.assessment_id, a2_h2.assessment_id, a2_h3.assessment_id),
        claim_assessment_ids=(c2.assessment_id,),
        diagnostic_conclusion_ids=(d2.conclusion_id,),
        open_question_ids=s1.open_question_ids,
        considered_action_ids=s1.considered_action_ids,
        repository=(("historical_reproduction_owner", "non-production compatibility"),),
        provenance_id=provenance.provenance_id,
    )
    t2 = StateTransition(
        transition_id="issue45:T2",
        predecessor_id=s1.state_id,
        successor_id=s2.state_id,
        delta=StateDelta(
            repository_delta=(("historical_reproduction_owner", "non-production compatibility"),)
        ),
        provenance_id=provenance.provenance_id,
    )

    _register(
        service,
        artifact,
        provenance,
        conditioning,
        runtime_availability,
        e_conditioning,
        e_raw,
        closure,
        h_conditioning,
        h_residual,
        h_formulation,
        scientific_claim,
        restart_question,
        action,
        decision,
        a0_h1,
        a0_h2,
        a0_h3,
        c0,
        execution,
        outcome,
        a1_h1,
        a1_h2,
        a1_h3,
        c1,
        d1,
        a2_h1,
        a2_h2,
        a2_h3,
        c2,
        d2,
    )
    service.commit_state(s0)
    service.commit_state(s1)
    service.commit_transition(t1)
    service.commit_state(s2)
    service.commit_transition(t2)

    fixture = HistoricalReplayFixture(
        fixture_id="issue45-89-scientific-closure",
        source_issues=(45, 46, 86, 87, 88, 89),
        available_sources=("GitHub Issue #45 final body", "persisted Issue45 interpretation summary"),
        provenance_quality="ISSUE_BODY_AND_PERSISTED_SUMMARY",
        initial_state_id=s0.state_id,
        expected_terminal_state_id=s2.state_id,
        expected_queries=(
            ("Q1_CURRENT_STATE", {"state_id": s2.state_id, "case_id": "issue45", "provenance_id": provenance.provenance_id}),
            ("Q9_REPOSITORY_ONLY_CHANGE", (t2.transition_id,)),
        ),
        missing_sources=("raw runtime evidence may be unavailable independently of persisted summary",),
        explicitly_unknown=("restart causality", "automatic scaling as unique root cause"),
    )
    return service, fixture


def _build_issue91_chain() -> tuple[OntologyService, HistoricalReplayFixture]:
    service = OntologyService()
    artifact = Artifact(
        artifact_id="issue91:body",
        uri="https://github.com/HyungseonSong-plasma/moose-test-repo/issues/91",
        media_type="text/markdown",
        provenance_id="issue91:prov",
    )
    provenance = ProvenanceRecord(
        provenance_id="issue91:prov",
        source_identity="GitHub Issue #91 final body",
        artifact_ids=(artifact.artifact_id,),
        metadata=(("quality", "ISSUE_BODY_AND_ACCEPTANCE_SUMMARY"),),
    )
    remedy_observation = Observation(
        observation_id="issue91:normalized-remedy",
        name="normalized_remedy_counterfactual",
        value="PASS",
        artifact_id=artifact.artifact_id,
        provenance_id=provenance.provenance_id,
    )
    remedy_evidence = Evidence(
        evidence_id="issue91:evidence-remedy",
        observation_id=remedy_observation.observation_id,
        context_id="issue91:normalization-counterfactual",
        provenance_id=provenance.provenance_id,
    )
    h_conditioning = Hypothesis(
        proposition_id="issue91:H-conditioning",
        statement="large dimensional state causes numerical conditioning/cancellation",
    )
    h_general_moose = Hypothesis(
        proposition_id="issue91:H-general-moose-defect",
        statement="a general MOOSE FV implementation defect causes the failure",
    )
    counterfactual_claim = ValidationClaim(
        proposition_id="issue91:claim-counterfactual",
        statement="normalization remedy counterfactual passes",
    )
    production_claim = ValidationClaim(
        proposition_id="issue91:claim-production",
        statement="normalized R3 is production accepted",
    )
    normalize = ActionSpec(
        action_id="issue91:action-normalize",
        intended_effect="test representation/conditioning hypothesis",
        target="electron_density_solver_representation",
        intervention_type="COUNTERFACTUAL_REPRESENTATION",
        discriminates=(h_conditioning.proposition_id, h_general_moose.proposition_id),
    )
    verify = ActionSpec(
        action_id="issue91:action-production-verify",
        intended_effect="verify normalized R3 on governed E0 and Econst cases",
        target="normalized_r3",
        intervention_type="PRODUCTION_VERIFICATION",
        discriminates=(production_claim.proposition_id,),
    )
    a0_h1 = HypothesisAssessment(
        assessment_id="issue91:A0-H1",
        hypothesis_id=h_conditioning.proposition_id,
        state_id="issue91:S0",
        support=HypothesisSupport.PLAUSIBLE,
    )
    a0_h2 = HypothesisAssessment(
        assessment_id="issue91:A0-H2",
        hypothesis_id=h_general_moose.proposition_id,
        state_id="issue91:S0",
        support=HypothesisSupport.PLAUSIBLE,
    )
    c0_cf = ClaimAssessment(
        assessment_id="issue91:C0-CF",
        claim_id=counterfactual_claim.proposition_id,
        state_id="issue91:S0",
        validation=ValidationStatus.UNASSESSED,
        acceptance=AcceptanceStatus.BLOCKED,
        production_readiness=ProductionReadiness.BLOCKED,
    )
    c0_prod = ClaimAssessment(
        assessment_id="issue91:C0-PROD",
        claim_id=production_claim.proposition_id,
        state_id="issue91:S0",
        validation=ValidationStatus.UNASSESSED,
        acceptance=AcceptanceStatus.BLOCKED,
        production_readiness=ProductionReadiness.BLOCKED,
    )
    d0 = SearchDecision(
        decision_id="issue91:decision-normalize",
        state_id="issue91:S0",
        action_id=normalize.action_id,
        disposition="SELECTED",
        rationale="bounded discriminator for representation conditioning",
    )
    s0 = DevelopmentState(
        state_id="issue91:S0",
        case_id="issue91",
        hypothesis_assessment_ids=(a0_h1.assessment_id, a0_h2.assessment_id),
        claim_assessment_ids=(c0_cf.assessment_id, c0_prod.assessment_id),
        considered_action_ids=(normalize.action_id,),
        provenance_id=provenance.provenance_id,
    )
    ex0 = ActionExecution(
        execution_id="issue91:execution-normalize",
        action_id=normalize.action_id,
        source_state_id=s0.state_id,
        status=ExecutionStatus.RUNNING,
        provenance_id=provenance.provenance_id,
    )
    out0 = ExecutionOutcome(
        outcome_id="issue91:outcome-normalize",
        execution_id=ex0.execution_id,
        status=ExecutionOutcomeStatus.SUCCEEDED,
        observation_ids=(remedy_observation.observation_id,),
    )
    a1_h1 = HypothesisAssessment(
        assessment_id="issue91:A1-H1",
        hypothesis_id=h_conditioning.proposition_id,
        state_id="issue91:S1",
        support=HypothesisSupport.STRONGLY_SUPPORTED,
        resolution=ResolutionStatus.RESOLVED,
        evidence_ids=(remedy_evidence.evidence_id,),
    )
    a1_h2 = HypothesisAssessment(
        assessment_id="issue91:A1-H2",
        hypothesis_id=h_general_moose.proposition_id,
        state_id="issue91:S1",
        support=HypothesisSupport.DISFAVORED,
        resolution=ResolutionStatus.RESOLVED,
        evidence_ids=(remedy_evidence.evidence_id,),
    )
    c1_cf = ClaimAssessment(
        assessment_id="issue91:C1-CF",
        claim_id=counterfactual_claim.proposition_id,
        state_id="issue91:S1",
        validation=ValidationStatus.VALIDATED,
        acceptance=AcceptanceStatus.ACCEPTED,
        production_readiness=ProductionReadiness.BLOCKED,
        evidence_ids=(remedy_evidence.evidence_id,),
    )
    c1_prod = ClaimAssessment(
        assessment_id="issue91:C1-PROD",
        claim_id=production_claim.proposition_id,
        state_id="issue91:S1",
        validation=ValidationStatus.UNASSESSED,
        acceptance=AcceptanceStatus.BLOCKED,
        production_readiness=ProductionReadiness.BLOCKED,
    )
    diag1 = DiagnosticConclusion(
        conclusion_id="issue91:D1",
        state_id="issue91:S1",
        statement="normalization counterfactual supports dimensional conditioning/cancellation; general MOOSE FV defect not established",
        proposition_ids=(h_conditioning.proposition_id, h_general_moose.proposition_id),
        evidence_ids=(remedy_evidence.evidence_id,),
        localized_owner="electron density solver representation",
        owner_granularity="OWNER_CLASS",
        provenance_id=provenance.provenance_id,
    )
    d1 = SearchDecision(
        decision_id="issue91:decision-production-verify",
        state_id="issue91:S1",
        action_id=verify.action_id,
        disposition="SELECTED",
        rationale="counterfactual PASS does not equal production acceptance",
    )
    s1 = DevelopmentState(
        state_id="issue91:S1",
        case_id="issue91",
        observation_ids=(remedy_observation.observation_id,),
        evidence_ids=(remedy_evidence.evidence_id,),
        hypothesis_assessment_ids=(a1_h1.assessment_id, a1_h2.assessment_id),
        claim_assessment_ids=(c1_cf.assessment_id, c1_prod.assessment_id),
        diagnostic_conclusion_ids=(diag1.conclusion_id,),
        considered_action_ids=(normalize.action_id, verify.action_id),
        provenance_id=provenance.provenance_id,
    )
    t1 = StateTransition(
        transition_id="issue91:T1",
        predecessor_id=s0.state_id,
        successor_id=s1.state_id,
        caused_by_execution_id=ex0.execution_id,
        delta=StateDelta(
            observation_delta=(remedy_observation.observation_id,),
            epistemic_delta=(a1_h1.assessment_id, a1_h2.assessment_id, diag1.conclusion_id),
            search_delta=(d0.decision_id, ex0.execution_id, out0.outcome_id, d1.decision_id),
            claim_delta=(c1_cf.assessment_id, c1_prod.assessment_id),
        ),
        provenance_id=provenance.provenance_id,
    )
    ex1 = ActionExecution(
        execution_id="issue91:execution-production-verify",
        action_id=verify.action_id,
        source_state_id=s1.state_id,
        status=ExecutionStatus.RUNNING,
        provenance_id=provenance.provenance_id,
    )
    out1 = ExecutionOutcome(
        outcome_id="issue91:outcome-production-verify",
        execution_id=ex1.execution_id,
        status=ExecutionOutcomeStatus.SUCCEEDED,
        message="governed R3 E0/Econst acceptance completed",
    )
    a2_h1 = HypothesisAssessment(
        assessment_id="issue91:A2-H1",
        hypothesis_id=h_conditioning.proposition_id,
        state_id="issue91:S2",
        support=a1_h1.support,
        resolution=a1_h1.resolution,
        scope=a1_h1.scope,
        evidence_ids=a1_h1.evidence_ids,
    )
    a2_h2 = HypothesisAssessment(
        assessment_id="issue91:A2-H2",
        hypothesis_id=h_general_moose.proposition_id,
        state_id="issue91:S2",
        support=a1_h2.support,
        resolution=a1_h2.resolution,
        scope=a1_h2.scope,
        evidence_ids=a1_h2.evidence_ids,
    )
    c2_cf = ClaimAssessment(
        assessment_id="issue91:C2-CF",
        claim_id=counterfactual_claim.proposition_id,
        state_id="issue91:S2",
        validation=c1_cf.validation,
        acceptance=c1_cf.acceptance,
        production_readiness=c1_cf.production_readiness,
        evidence_ids=c1_cf.evidence_ids,
    )
    c2_prod = ClaimAssessment(
        assessment_id="issue91:C2-PROD",
        claim_id=production_claim.proposition_id,
        state_id="issue91:S2",
        validation=ValidationStatus.VALIDATED,
        acceptance=AcceptanceStatus.ACCEPTED,
        production_readiness=ProductionReadiness.READY,
        evidence_ids=(remedy_evidence.evidence_id,),
        provenance_id=provenance.provenance_id,
    )
    diag2 = DiagnosticConclusion(
        conclusion_id="issue91:D2",
        state_id="issue91:S2",
        statement=diag1.statement,
        proposition_ids=diag1.proposition_ids,
        evidence_ids=diag1.evidence_ids,
        localized_owner=diag1.localized_owner,
        owner_granularity=diag1.owner_granularity,
        mechanism_id=diag1.mechanism_id,
        provenance_id=provenance.provenance_id,
    )
    s2 = DevelopmentState(
        state_id="issue91:S2",
        case_id="issue91",
        observation_ids=s1.observation_ids,
        evidence_ids=s1.evidence_ids,
        hypothesis_assessment_ids=(a2_h1.assessment_id, a2_h2.assessment_id),
        claim_assessment_ids=(c2_cf.assessment_id, c2_prod.assessment_id),
        diagnostic_conclusion_ids=(diag2.conclusion_id,),
        considered_action_ids=s1.considered_action_ids,
        provenance_id=provenance.provenance_id,
    )
    t2 = StateTransition(
        transition_id="issue91:T2",
        predecessor_id=s1.state_id,
        successor_id=s2.state_id,
        caused_by_execution_id=ex1.execution_id,
        delta=StateDelta(
            search_delta=(ex1.execution_id, out1.outcome_id),
            claim_delta=(c2_prod.assessment_id,),
        ),
        provenance_id=provenance.provenance_id,
    )

    _register(
        service,
        artifact,
        provenance,
        remedy_observation,
        remedy_evidence,
        h_conditioning,
        h_general_moose,
        counterfactual_claim,
        production_claim,
        normalize,
        verify,
        a0_h1,
        a0_h2,
        c0_cf,
        c0_prod,
        d0,
        ex0,
        out0,
        a1_h1,
        a1_h2,
        c1_cf,
        c1_prod,
        diag1,
        d1,
        ex1,
        out1,
        a2_h1,
        a2_h2,
        c2_cf,
        c2_prod,
        diag2,
    )
    service.commit_state(s0)
    service.commit_state(s1)
    service.commit_transition(t1)
    service.commit_state(s2)
    service.commit_transition(t2)

    fixture = HistoricalReplayFixture(
        fixture_id="issue91-98-fault-isolation",
        source_issues=(91, 92, 93, 94, 98),
        available_sources=("GitHub Issue #91 final body", "Issue #94/#98 remedy summaries"),
        provenance_quality="ISSUE_BODY_AND_ACCEPTANCE_SUMMARY",
        initial_state_id=s0.state_id,
        expected_terminal_state_id=s2.state_id,
        expected_queries=(
            ("Q1_CURRENT_STATE", {"state_id": s2.state_id, "case_id": "issue91", "provenance_id": provenance.provenance_id}),
            ("Q9_REPOSITORY_ONLY_CHANGE", ()),
        ),
        explicitly_unknown=("general MOOSE FV defect is not established",),
    )
    return service, fixture


def test_historical_coverage_catalog_has_required_corpus_and_complete_contract():
    catalog = historical_coverage_catalog()
    for fixture in catalog:
        validate_fixture_contract(fixture)
    covered = {issue for fixture in catalog for issue in fixture.source_issues}
    assert {18, 19, 20, 23, 31, 44, 45, 46, 86, 87, 88, 89, 91, 92, 93, 94, 98} <= covered
    assert {fixture.fixture_id for fixture in catalog} == {
        "issue18-active-kernel-coverage",
        "issue19-checker-representation",
        "issue20-environment-jit",
        "issue23-harness-intervention",
        "issue31-metric-applicability",
        "issue44-observation-time-identity",
        "issue45-89-scientific-closure",
        "issue91-98-fault-isolation",
    }


def test_issue45_replay_answers_q1_to_q9_and_preserves_repository_only_transition():
    service, fixture = _build_issue45_chain()
    acceptance = evaluate_historical_replay(service, fixture, case_id="issue45")
    assert acceptance.passed, acceptance.mismatches
    assert tuple(item[0] for item in acceptance.query_results) == QUERY_IDS
    results = acceptance.result_map()
    assert results["Q9_REPOSITORY_ONLY_CHANGE"] == ("issue45:T2",)
    current_claim = results["Q7_CLAIM_READINESS"][0]
    assert current_claim[1] == ValidationStatus.VALIDATED.value
    assert current_claim[3] == AcceptanceStatus.ACCEPTED.value
    assert current_claim[4] == ProductionReadiness.BLOCKED.value
    assert results["Q8_ABSENCE_SCOPE"]["unavailable_evidence"] == (
        ("issue45:evidence-raw-runtime", EvidenceAvailability.UNAVAILABLE.value, EvidenceAdmissibility.UNKNOWN.value),
    )
    diagnostic = results["Q2_EPISTEMIC_PARTITION"]["diagnostics"][0]
    assert diagnostic[2] == "OWNER_CLASS"
    assert diagnostic[3] is None


def test_issue45_replay_round_trip_preserves_all_query_answers(tmp_path):
    service, _ = _build_issue45_chain()
    before = run_replay_queries(service, case_id="issue45")
    persisted = service.save_json(tmp_path / "issue45-ontology.json")
    reloaded = OntologyService.load_json(persisted)
    after = run_replay_queries(reloaded, case_id="issue45")
    assert after == before


def test_issue91_replay_separates_counterfactual_pass_from_production_acceptance():
    service, fixture = _build_issue91_chain()
    acceptance = evaluate_historical_replay(service, fixture, case_id="issue91")
    assert acceptance.passed, acceptance.mismatches

    s1_counterfactual = service.get("issue91:C1-CF")
    s1_production = service.get("issue91:C1-PROD")
    out0 = service.get("issue91:outcome-normalize")
    assert out0.status is ExecutionOutcomeStatus.SUCCEEDED
    assert s1_counterfactual.validation is ValidationStatus.VALIDATED
    assert s1_counterfactual.production_readiness is ProductionReadiness.BLOCKED
    assert s1_production.validation is ValidationStatus.UNASSESSED
    assert s1_production.acceptance is AcceptanceStatus.BLOCKED

    current = acceptance.result_map()["Q7_CLAIM_READINESS"]
    by_claim = {item[0]: item for item in current}
    assert by_claim["issue91:claim-production"][1:5] == (
        ValidationStatus.VALIDATED.value,
        ApplicabilityStatus.APPLICABLE.value,
        AcceptanceStatus.ACCEPTED.value,
        ProductionReadiness.READY.value,
    )


def test_issue91_replay_round_trip_preserves_all_query_answers(tmp_path):
    service, _ = _build_issue91_chain()
    before = run_replay_queries(service, case_id="issue91")
    persisted = service.save_json(tmp_path / "issue91-ontology.json")
    reloaded = OntologyService.load_json(persisted)
    assert run_replay_queries(reloaded, case_id="issue91") == before


def test_hard_semantic_distinctions_are_not_collapsed():
    missing = Evidence(
        evidence_id="inv:e-missing",
        observation_id="inv:o",
        context_id="inv:ctx",
        availability=EvidenceAvailability.MISSING,
        admissibility=EvidenceAdmissibility.UNKNOWN,
    )
    synthetic = Evidence(
        evidence_id="inv:e-synthetic",
        observation_id="inv:o2",
        context_id="inv:ctx",
        availability=EvidenceAvailability.AVAILABLE,
        admissibility=EvidenceAdmissibility.NON_EVIDENTIARY,
    )
    scoped = HypothesisAssessment(
        assessment_id="inv:h",
        hypothesis_id="inv:H",
        state_id="inv:S",
        support=HypothesisSupport.PLAUSIBLE,
        scope=ScopeStatus.OUT_OF_SCOPE,
    )
    not_applicable = ClaimAssessment(
        assessment_id="inv:c",
        claim_id="inv:C",
        state_id="inv:S",
        validation=ValidationStatus.UNASSESSED,
        applicability=ApplicabilityStatus.NOT_APPLICABLE,
        acceptance=AcceptanceStatus.BLOCKED,
        production_readiness=ProductionReadiness.NOT_ASSESSED,
    )
    degenerate = ClaimAssessment(
        assessment_id="inv:c-degenerate",
        claim_id="inv:C2",
        state_id="inv:S",
        validation=ValidationStatus.UNASSESSED,
        applicability=ApplicabilityStatus.DEGENERATE,
        acceptance=AcceptanceStatus.BLOCKED,
    )
    succeeded = ExecutionOutcome(
        outcome_id="inv:outcome",
        execution_id="inv:execution",
        status=ExecutionOutcomeStatus.SUCCEEDED,
    )

    assert missing.availability is not EvidenceAvailability.AVAILABLE
    assert missing.admissibility is not EvidenceAdmissibility.NON_EVIDENTIARY
    assert synthetic.admissibility is EvidenceAdmissibility.NON_EVIDENTIARY
    assert scoped.support is HypothesisSupport.PLAUSIBLE
    assert scoped.scope is ScopeStatus.OUT_OF_SCOPE
    assert not_applicable.applicability is ApplicabilityStatus.NOT_APPLICABLE
    assert not_applicable.validation is ValidationStatus.UNASSESSED
    assert degenerate.applicability is ApplicabilityStatus.DEGENERATE
    assert degenerate.acceptance is AcceptanceStatus.BLOCKED
    assert succeeded.status is ExecutionOutcomeStatus.SUCCEEDED


def test_canonical_semantic_path_has_no_recipe_or_issue_runner_dependency():
    canonical_files = [
        ROOT / "qpx_harness" / "application" / "gateway.py",
        ROOT / "qpx_harness" / "specification" / "compiler.py",
        ROOT / "qpx_harness" / "planning" / "policy.py",
        ROOT / "qpx_harness" / "execution" / "compiler.py",
        ROOT / "qpx_harness" / "adapters" / "moose" / "target.py",
    ]
    for path in canonical_files:
        text = path.read_text(encoding="utf-8")
        assert "recipes." not in text, path
        assert "application.protocols" not in text, path
        assert "Issue26_" not in text, path
    assert not (ROOT / "recipes").exists()
    historical = __import__("experiments.historical_recipe_support", fromlist=["*"])
    assert historical is not None
