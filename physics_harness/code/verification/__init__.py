"""Evidence-driven, policy-free Code Verification v0.1.

Source-snapshot verification is not evidence of runtime or semantic parity.
"""

from .consistency import VerificationReceipt, verify_generated_artifact
from .dependencies import (
    ChangeVerificationPlan, DependencyContract, DependencyFinding,
    DependencyRule, DependencyVerification, plan_change_verification,
    verify_dependencies, verify_dependency_repository,
    DependencyObservation, DependencyDesignReport, analyze_independent_dependencies,
)
from .naming_provenance import (
    NamingSourceVerification, verify_naming_evidence_sources,
)

from .naming_boundary import OwnedSymbol, ResponsibilityBinding, NamingBoundaryReceipt, verify_naming_boundary
from .naming_candidate import CandidatePlacement, NamingCandidateReceipt, verify_naming_candidate

__all__ = [
    "OwnedSymbol", "ResponsibilityBinding", "NamingBoundaryReceipt", "verify_naming_boundary",
    "CandidatePlacement", "NamingCandidateReceipt", "verify_naming_candidate",
    "ChangeVerificationPlan", "VerificationReceipt",
    "plan_change_verification", "verify_generated_artifact",
    "DependencyContract", "DependencyFinding", "DependencyRule",
    "DependencyVerification", "verify_dependencies",
    "verify_dependency_repository",
    "DependencyObservation", "DependencyDesignReport", "analyze_independent_dependencies",
    "NamingSourceVerification", "verify_naming_evidence_sources",
]

from .naming_behavior import (
    ExecutableComparison, NamingBehaviorReceipt, verify_naming_behavior_projection,
)
from .naming_consumers import (
    ConsumerReference, NamingConsumerReceipt, audit_naming_consumers,
    ModulePathTransitionReceipt, verify_module_path_transition,
)
from .naming_semantic_review import (
    BlindedSourceExcerpt, BlindedSemanticPacket, IndependentResponsibilityHypothesis,
    SecondPassSemanticChallenge, SemanticReviewReceipt,
    build_blinded_semantic_packet, review_semantic_challenge,
)
from .naming_gates import NamingSafetyGateReport, evaluate_naming_safety_gates

__all__ += [
    "ExecutableComparison", "NamingBehaviorReceipt", "verify_naming_behavior_projection",
    "ConsumerReference", "NamingConsumerReceipt", "audit_naming_consumers",
    "ModulePathTransitionReceipt", "verify_module_path_transition",
    "BlindedSourceExcerpt", "BlindedSemanticPacket", "IndependentResponsibilityHypothesis",
    "SecondPassSemanticChallenge", "SemanticReviewReceipt",
    "build_blinded_semantic_packet", "review_semantic_challenge",
    "NamingSafetyGateReport", "evaluate_naming_safety_gates",
]

from .junit_compare import ReplayArtifact, ReplayComparison, compare_replay_artifacts, compare_candidate_replay
__all__ += ["ReplayArtifact", "ReplayComparison", "compare_replay_artifacts", "compare_candidate_replay"]

from .pytest_revision_runner import (
    NamingReplayRun, NamingReplayReceipt, run_naming_test_replay,
    build_executed_replay_artifact_pair,
)
from .naming_review_authority import (
    NamingReviewAuthorityReceipt, naming_review_context_sha256,
    verify_github_naming_review,
)
__all__ += [
    "NamingReplayRun", "NamingReplayReceipt", "run_naming_test_replay",
    "build_executed_replay_artifact_pair",
    "NamingReviewAuthorityReceipt", "naming_review_context_sha256",
    "verify_github_naming_review",
]

from .naming_actions import (
    GitHubActionsRestReader, ActionsArtifactReceipt, ActionsReplayGate,
    verify_actions_junit_artifact, compare_actions_junit_replays, audit_actions_replay,
)
__all__ += [
    "GitHubActionsRestReader", "ActionsArtifactReceipt", "ActionsReplayGate",
    "verify_actions_junit_artifact", "compare_actions_junit_replays", "audit_actions_replay",
]
