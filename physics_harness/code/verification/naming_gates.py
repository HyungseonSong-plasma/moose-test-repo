"""Compose independent read-only rename/extract checks without certifying safety.

Every underlying receipt is recomputed from immutable Git objects. The
orchestrator does not accept a plain-text model PASS or mutable caller-supplied
receipt as authority. It produces one bounded, interpretable HOLD/BLOCKED
surface for an actual isolated candidate revision.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..diagnostics.providers.git import GitSourceProvider
from ..refactor.naming import NamingCase, NamingOption
from .junit_compare import ReplayArtifact, ReplayComparison, compare_candidate_replay
from .naming_boundary import ResponsibilityBinding
from .naming_candidate import CandidatePlacement, NamingCandidateReceipt, verify_naming_candidate
from .naming_behavior import NamingBehaviorReceipt, verify_naming_behavior_projection
from .naming_consumers import (
    NamingConsumerReceipt, ModulePathTransitionReceipt, audit_naming_consumers,
    verify_module_path_transition,
)
from .naming_semantic_review import (
    BlindedSemanticPacket, IndependentResponsibilityHypothesis,
    SecondPassSemanticChallenge, SemanticReviewReceipt,
    build_blinded_semantic_packet, review_semantic_challenge,
)


@dataclass(frozen=True, slots=True)
class NamingSafetyGateReport:
    baseline_revision: str
    candidate_revision: str
    option_id: str
    status: str  # BLOCKED / HOLD; never an execution approval
    structural: NamingCandidateReceipt
    behavior: NamingBehaviorReceipt
    consumers: NamingConsumerReceipt
    blind_review_packet: BlindedSemanticPacket
    semantic_review: SemanticReviewReceipt | None
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]
    required_checks: tuple[str, ...]
    replay: ReplayComparison | None = None
    module_transition: ModulePathTransitionReceipt | None = None

    @property
    def mutation_approved(self) -> bool:
        return False

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False


def evaluate_naming_safety_gates(
    case: NamingCase, option: NamingOption, provider: GitSourceProvider,
    bindings: tuple[ResponsibilityBinding, ...], candidate_revision: str,
    candidate_owner_path: str, placements: tuple[CandidatePlacement, ...],
    *, reviewer_hypotheses: tuple[IndependentResponsibilityHypothesis, ...] | None = None,
    reviewer_challenge: SecondPassSemanticChallenge | None = None,
    max_consumer_files: int = 3000,
    max_consumer_bytes: int = 20_000_000,
    replay_baseline: ReplayArtifact | None = None,
    replay_candidate: ReplayArtifact | None = None,
) -> NamingSafetyGateReport:
    """One revision-bound result, recomputed without trusting model assertions.

    The independent reviewer inputs are intentionally advisory until external
    identity and semantic authenticity are established. This module performs no
    code execution, PR merge, persistent edit or repository mutation.
    """
    structural = verify_naming_candidate(case, option, provider, bindings,
        candidate_revision, candidate_owner_path, placements)
    behavior = verify_naming_behavior_projection(case, option, provider, bindings,
        candidate_revision, candidate_owner_path, placements)
    consumers = audit_naming_consumers(case, option, provider, candidate_revision,
        placements, max_files=max_consumer_files, max_bytes=max_consumer_bytes)
    blind = build_blinded_semantic_packet(case, provider, bindings)
    semantic = None
    blocked = set(structural.blockers) | set(behavior.blockers) | set(consumers.blockers)
    unresolved = set(structural.unresolved) | set(behavior.unresolved) | set(consumers.unresolved) | set(blind.unresolved)
    checks = set(structural.required_checks) | set(behavior.required_checks) | set(consumers.required_checks)
    transition = None
    if candidate_owner_path != case.current_path:
        if option.module_path_policy is None:
            unresolved.add("MODULE_PATH_POLICY_UNDECLARED")
        elif case.target_kind == "FILE":
            transition = verify_module_path_transition(
                provider, case.revision, candidate_revision, case.current_path,
                candidate_owner_path, option.module_path_policy,
                max_files=max_consumer_files, max_bytes=max_consumer_bytes)
            blocked.update(transition.blockers)
            unresolved.update(transition.unresolved)
        else:
            unresolved.add("MODULE_PATH_TRANSITION_SCOPE_UNSUPPORTED")
    checks.update({"AUTHENTICATED_INDEPENDENT_SEMANTIC_REVIEW",
                   "TRUSTED_EXACT_COMMIT_BEFORE_AFTER_TEST_RUN",
                   "VERIFIED_EXTERNAL_CONSUMER_SCOPE",
                   "POST_INTEGRATION_SHA_VERIFICATION_AND_ROLLBACK"})
    if (reviewer_hypotheses is None) != (reviewer_challenge is None):
        unresolved.add("INCOMPLETE_TWO_PASS_SEMANTIC_REVIEW")
    elif reviewer_hypotheses is not None and reviewer_challenge is not None:
        semantic = review_semantic_challenge(blind, reviewer_hypotheses,
                                             reviewer_challenge, option)
        blocked.update(semantic.blockers)
        unresolved.update(semantic.unresolved)
        checks.update(semantic.required_checks)
    else:
        unresolved.add("INDEPENDENT_TWO_PASS_SEMANTIC_REVIEW_MISSING")
    replay = None
    if (replay_baseline is None) != (replay_candidate is None):
        unresolved.add("INCOMPLETE_EXACT_REVISION_TEST_REPLAY")
    elif replay_baseline is not None and replay_candidate is not None:
        replay = compare_candidate_replay(case.revision, candidate_revision,
                                          replay_baseline, replay_candidate)
        blocked.update(replay.blockers)
        unresolved.update(replay.unresolved)
    else:
        unresolved.add("EXACT_REVISION_TEST_REPLAY_NOT_PROVIDED")
    checks.update({"AUTHENTICATE_TEST_ARTIFACT_PRODUCER",
                   "VERIFY_TEST_ARTIFACT_EXACT_CHECKOUT_AND_TOOLCHAIN"})
    # The branch is intentionally no stronger than BLOCKED/HOLD: semantic
    # evaluation and authenticated behavioral execution are not implemented here.
    return NamingSafetyGateReport(case.revision, candidate_revision, option.id,
        "BLOCKED" if blocked else "HOLD", structural, behavior, consumers,
        blind, semantic, tuple(sorted(blocked)), tuple(sorted(unresolved)),
        tuple(sorted(checks)), replay, transition)


__all__ = ["NamingSafetyGateReport", "evaluate_naming_safety_gates"]
