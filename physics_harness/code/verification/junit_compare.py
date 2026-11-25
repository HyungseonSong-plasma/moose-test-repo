"""Exact-revision before/after test replay evidence, without execution authority.

This module only evaluates supplied JUnit bytes and immutable content hashes.
It cannot authenticate the CI producer, attest a checkout, or prove equivalence.
Those obligations are intentionally returned as unresolved requirements.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from libs.test_verification.junit import parse_junit, compare_case_outcomes

_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True, slots=True)
class ReplayArtifact:
    revision: str
    junit_xml: bytes
    expected_sha256: str
    run_reference: str


@dataclass(frozen=True, slots=True)
class ReplayComparison:
    baseline_revision: str
    candidate_revision: str
    status: str  # BLOCKED / HOLD, never PASS for mutation
    baseline_cases: tuple[str, ...]
    candidate_cases: tuple[str, ...]
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False


def _parse(artifact: ReplayArtifact, *, max_bytes: int) -> tuple[dict[str, str], set[str], set[str]]:
    blocked: set[str] = set()
    unresolved: set[str] = set()
    if not _SHA.fullmatch(artifact.revision):
        blocked.add("INVALID_REVISION")
    if not re.fullmatch(r"[0-9a-f]{64}", artifact.expected_sha256):
        blocked.add("INVALID_ARTIFACT_DIGEST")
    if not artifact.run_reference.strip():
        unresolved.add("MISSING_RUN_REFERENCE")
    cases, findings, gaps = parse_junit(
        artifact.junit_xml, artifact.expected_sha256, max_bytes=max_bytes)
    return cases, blocked | findings, unresolved | gaps


def compare_replay_artifacts(
    baseline: ReplayArtifact,
    candidate: ReplayArtifact,
    *,
    max_xml_bytes: int = 8_000_000,
) -> ReplayComparison:
    """Compare exact raw artifact bytes and stable testcase identities.

    An identical suite with no failures is necessary but not sufficient for a
    safe rename. CI producer identity and exact checkout must be authenticated
    separately; neither a run URL nor caller-supplied SHA is an attestation.
    """
    if not isinstance(baseline, ReplayArtifact) or not isinstance(candidate, ReplayArtifact):
        raise TypeError("REPLAY_ARTIFACTS_REQUIRED")
    if type(max_xml_bytes) is not int or max_xml_bytes < 1:
        raise ValueError("INVALID_REPLAY_BUDGET")
    before, b1, u1 = _parse(baseline, max_bytes=max_xml_bytes)
    after, b2, u2 = _parse(candidate, max_bytes=max_xml_bytes)
    blocked = b1 | b2
    unresolved = u1 | u2
    if baseline.revision == candidate.revision:
        blocked.add("CANDIDATE_REVISION_NOT_DISTINCT")
    findings, gaps = compare_case_outcomes(before, after)
    blocked.update(findings)
    unresolved.update(gaps)
    unresolved.update({
        "AUTHENTICATE_CI_PRODUCER_AND_ARTIFACT_ORIGIN",
        "VERIFY_EXACT_CHECKOUT_TOOLCHAIN_AND_TEST_COMMAND",
        "VERIFY_EXTERNAL_CONSUMERS_AND_PUBLIC_CONTRACTS",
        "VERIFY_SEMANTIC_REVIEWER_INDEPENDENCE",
        "POST_INTEGRATION_SHA_AND_ROLLBACK_REQUIRED",
    })
    return ReplayComparison(
        baseline.revision, candidate.revision,
        "BLOCKED" if blocked else "HOLD",
        tuple(sorted(before)), tuple(sorted(after)),
        tuple(sorted(blocked)), tuple(sorted(unresolved)),
    )


def compare_candidate_replay(
    baseline_revision: str,
    candidate_revision: str,
    baseline: ReplayArtifact,
    candidate: ReplayArtifact,
) -> ReplayComparison:
    """Bind supplied replay bytes to the exact revisions under naming review.

    This is an additional fail-closed check, not CI producer authentication.
    """
    result = compare_replay_artifacts(baseline, candidate)
    if baseline.revision == baseline_revision and candidate.revision == candidate_revision:
        return result
    from dataclasses import replace
    return replace(result, status="BLOCKED", blockers=tuple(sorted(set(result.blockers) | {
        "REPLAY_REVISION_DOES_NOT_MATCH_NAMING_CANDIDATE",
    })))


__all__ = ["ReplayArtifact", "ReplayComparison", "compare_replay_artifacts", "compare_candidate_replay"]
