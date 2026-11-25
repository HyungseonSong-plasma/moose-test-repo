"""Read-only GitHub Actions provenance and JUnit artifact gate for naming candidates.

This module obtains GitHub data via HTTPS (or an explicitly injected test source)
then independently checks run/job/artifact relationships and actual archive bytes.
Neither GitHub run success nor archive consistency attests the executed source,
workflow trust, dependencies, toolchain, external consumers or semantic parity.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from xml.etree import ElementTree as ET

# Compatibility re-exports: retain public object identity and existing callers.
from libs.git_evidence import (
    ActionsReadSource, GitHubActionsRestReader, read_actions_archive_members,
)

from .junit_compare import ReplayArtifact, ReplayComparison, compare_candidate_replay

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


@dataclass(frozen=True, slots=True)
class ActionsArtifactReceipt:
    repository: str
    revision: str
    run_id: int
    run_attempt: int | None
    job_name: str
    artifact_name: str
    artifact_id: int | None
    status: str  # BLOCKED / HOLD / GITHUB_METADATA_WITNESSED
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]
    junit_xml: bytes = b""
    junit_sha256: str = ""
    archive_sha256: str = ""
    junit_entry: str = ""
    source: str = "INJECTED_READER"

    @property
    def mutation_approved(self) -> bool:
        return False

    @property
    def producer_authenticated(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ActionsReplayGate:
    baseline: ActionsArtifactReceipt
    candidate: ActionsArtifactReceipt
    replay: ReplayComparison | None
    status: str  # BLOCKED / HOLD
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False


def _junit_from_archive(archive: bytes, entry: str | None) -> tuple[bytes, str]:
    try:
        members = read_actions_archive_members(
            archive, entries=(entry,) if entry else None, suffix=".xml")
    except ValueError as exc:
        if str(exc) == "ARCHIVE_MEMBER_AMBIGUOUS_OR_MISSING":
            raise ValueError("JUNIT_XML_AMBIGUOUS_OR_MISSING") from exc
        raise
    selected, xml = next(iter(members.items()))
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("JUNIT_XML_DTD_OR_ENTITY")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("INVALID_JUNIT_XML") from exc
    if root.tag not in {"testsuites", "testsuite"}:
        raise ValueError("INVALID_JUNIT_ROOT")
    return xml, selected


def verify_actions_junit_artifact(
    repository: str, revision: str, run_id: int, *, job_name: str,
    artifact_name: str, workflow_path: str, source: ActionsReadSource | None = None,
    junit_entry: str | None = None, required_step_names: tuple[str, ...] = (),
) -> ActionsArtifactReceipt:
    """Read exact GitHub API run/job/artifact, not a caller's success claims.

    A fixture reader supports deterministic tests but cannot be mistaken for
    independent provider proof. Real REST reads still require signed build
    attestations and exact environment validation before mutation approval.
    """
    if not isinstance(repository, str) or not _REPO.fullmatch(repository):
        raise ValueError("INVALID_ACTIONS_REPOSITORY")
    if not isinstance(revision, str) or not _SHA.fullmatch(revision):
        raise ValueError("INVALID_ACTIONS_REVISION")
    if type(run_id) is not int or run_id < 1:
        raise ValueError("INVALID_ACTIONS_RUN_ID")
    if any(not isinstance(x, str) or not x.strip() for x in (job_name, artifact_name, workflow_path)):
        raise ValueError("INVALID_ACTIONS_SELECTOR")
    if not isinstance(required_step_names, tuple) or any(not isinstance(x, str) or not x for x in required_step_names):
        raise ValueError("INVALID_STEP_SELECTOR")
    if junit_entry is not None and (not isinstance(junit_entry, str) or not junit_entry.endswith(".xml")):
        raise ValueError("INVALID_JUNIT_ENTRY")
    reader = source if source is not None else GitHubActionsRestReader()
    source_kind = "GITHUB_REST_HTTPS" if type(reader) is GitHubActionsRestReader else "INJECTED_READER"
    blocked: set[str] = set()
    unknown: set[str] = {
        "RUNNER_IDENTITY_AND_TOOLCHAIN_NOT_ATTESTED",
        "WORKFLOW_CONFIGURATION_AND_DEPENDENCY_IMMUTABILITY_UNVERIFIED",
        "EXTERNAL_CONSUMERS_AND_SEMANTIC_PARITY_NOT_PROVEN",
    }
    if source_kind == "INJECTED_READER":
        unknown.add("INJECTED_SOURCE_NOT_GITHUB_AUTHENTICATION")
    archive_sha = ""
    xml = b""
    xml_name = ""
    chosen_id = None
    attempt = None
    try:
        run = reader.run(repository, run_id)
        if not isinstance(run, dict):
            raise ValueError("ACTIONS_RUN_JSON_INVALID")
        attempt = run.get("run_attempt")
        if run.get("id") != run_id or run.get("repository", {}).get("full_name") != repository:
            blocked.add("RUN_REPOSITORY_OR_ID_MISMATCH")
        if run.get("head_sha") != revision:
            blocked.add("ACTIONS_RUN_NOT_EXACT_REVISION")
        if run.get("path") != workflow_path:
            blocked.add("WORKFLOW_PATH_MISMATCH")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            blocked.add("ACTIONS_RUN_NOT_SUCCESSFUL")
        if type(attempt) is not int or attempt < 1:
            blocked.add("RUN_ATTEMPT_UNKNOWN")
        elif attempt > 1:
            unknown.add("ARTIFACT_RUN_ATTEMPT_NOT_PROVEN")
        jobs = reader.jobs(repository, run_id)
        if not isinstance(jobs, list):
            raise ValueError("ACTIONS_JOBS_JSON_INVALID")
        matching = [j for j in jobs if j.get("name") == job_name]
        if len(matching) != 1:
            blocked.add("REQUIRED_JOB_MISSING_OR_AMBIGUOUS")
        else:
            job = matching[0]
            if job.get("conclusion") != "success" or job.get("status") != "completed":
                blocked.add("REQUIRED_JOB_DID_NOT_PASS")
            steps = job.get("steps") or []
            for name in required_step_names:
                observed = [s for s in steps if s.get("name") == name]
                if len(observed) != 1 or observed[0].get("conclusion") != "success":
                    blocked.add("REQUIRED_JOB_STEP_NOT_PASSED:" + name)
        if blocked:
            return ActionsArtifactReceipt(repository, revision, run_id, attempt, job_name,
                artifact_name, None, "BLOCKED", tuple(sorted(blocked)), tuple(sorted(unknown)), source=source_kind)
        artifacts = reader.artifacts(repository, run_id)
        if not isinstance(artifacts, list):
            raise ValueError("ACTIONS_ARTIFACTS_JSON_INVALID")
        selected = [a for a in artifacts if a.get("name") == artifact_name]
        if not selected:
            unknown.add("JUNIT_ARTIFACT_NOT_UPLOADED")
        elif len(selected) != 1:
            blocked.add("AMBIGUOUS_JUNIT_ARTIFACT_NAME")
        else:
            a = selected[0]
            chosen_id = a.get("id")
            if type(chosen_id) is not int or chosen_id < 1:
                blocked.add("INVALID_GITHUB_ARTIFACT_ID")
            if a.get("expired") is not False:
                unknown.add("ACTIONS_ARTIFACT_EXPIRED_OR_UNKNOWN")
            owner = a.get("workflow_run") or {}
            if owner.get("id") != run_id or owner.get("head_sha") != revision:
                blocked.add("ARTIFACT_RUN_SHA_ASSOCIATION_MISMATCH")
            run_repo_id = (run.get("repository") or {}).get("id")
            if run_repo_id is not None and owner.get("repository_id") != run_repo_id:
                blocked.add("ARTIFACT_REPOSITORY_ASSOCIATION_MISMATCH")
            if not blocked and "ACTIONS_ARTIFACT_EXPIRED_OR_UNKNOWN" not in unknown:
                archive = reader.archive(repository, chosen_id)
                if not isinstance(archive, bytes):
                    raise ValueError("ARCHIVE_NOT_BYTES")
                archive_sha = sha256(archive).hexdigest()
                xml, xml_name = _junit_from_archive(archive, junit_entry)
                # Guard against a new run attempt or run status changing while
                # archive and jobs were fetched. The archive itself does not
                # expose an attempt identifier.
                again = reader.run(repository, run_id)
                identity_fields = ("id", "head_sha", "run_attempt", "status", "conclusion")
                if not isinstance(again, dict) or any(run.get(k) != again.get(k) for k in identity_fields):
                    blocked.add("ACTIONS_RUN_CHANGED_DURING_READ")
                # The replay parser validates exact XML, testcase IDs, failure
                # statuses and duplicate identities after pairing both revisions.
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        unknown.add("GITHUB_SOURCE_OR_ARCHIVE_UNAVAILABLE:" + type(exc).__name__)
        if isinstance(exc, ValueError):
            blocked.add("GITHUB_SOURCE_OR_ARCHIVE_INVALID:" + str(exc))
    status = "BLOCKED" if blocked else "HOLD" if not xml else "GITHUB_METADATA_WITNESSED"
    return ActionsArtifactReceipt(repository, revision, run_id, attempt,
        job_name, artifact_name, chosen_id, status, tuple(sorted(blocked)),
        tuple(sorted(unknown)), xml, sha256(xml).hexdigest() if xml else "",
        archive_sha, xml_name, source_kind)


def compare_actions_junit_replays(
    baseline: ActionsArtifactReceipt, candidate: ActionsArtifactReceipt,
) -> ActionsReplayGate:
    """Compare source-derived archive bytes; never promote to mutation permit."""
    if not isinstance(baseline, ActionsArtifactReceipt) or not isinstance(candidate, ActionsArtifactReceipt):
        raise TypeError("ACTIONS_RECEIPTS_REQUIRED")
    blocked = set(baseline.blockers) | set(candidate.blockers)
    unknown = set(baseline.unresolved) | set(candidate.unresolved)
    if baseline.repository != candidate.repository:
        blocked.add("CROSS_REPOSITORY_ACTIONS_REPLAY")
    if baseline.revision == candidate.revision:
        blocked.add("ACTIONS_REPLAY_REVISIONS_NOT_DISTINCT")
    comparison = None
    if baseline.junit_xml and candidate.junit_xml and not blocked:
        comparison = compare_candidate_replay(
            baseline.revision, candidate.revision,
            ReplayArtifact(baseline.revision, baseline.junit_xml, baseline.junit_sha256,
                           f"github-actions-run:{baseline.run_id}:{baseline.artifact_id}"),
            ReplayArtifact(candidate.revision, candidate.junit_xml, candidate.junit_sha256,
                           f"github-actions-run:{candidate.run_id}:{candidate.artifact_id}"),
        )
        blocked.update(comparison.blockers)
        unknown.update(comparison.unresolved)
    else:
        unknown.add("JUNIT_SOURCE_REPLAY_NOT_AVAILABLE")
    return ActionsReplayGate(baseline, candidate, comparison,
                             "BLOCKED" if blocked else "HOLD",
                             tuple(sorted(blocked)), tuple(sorted(unknown)))


def audit_actions_replay(
    repository: str, baseline_revision: str, candidate_revision: str,
    baseline_run_id: int, candidate_run_id: int, *, job_name: str,
    artifact_name: str, workflow_path: str, source: ActionsReadSource | None = None,
    junit_entry: str | None = None, required_step_names: tuple[str, ...] = (),
) -> ActionsReplayGate:
    """Fetch both official run/artifact chains, then bind and compare bytes.

    This is the API-facing entrypoint; no caller-provided PASS/receipt is used.
    The same source adapter is reused to keep repository/scope consistent.
    """
    reader = source if source is not None else GitHubActionsRestReader()
    kwargs = dict(job_name=job_name, artifact_name=artifact_name,
                  workflow_path=workflow_path, source=reader,
                  junit_entry=junit_entry, required_step_names=required_step_names)
    before = verify_actions_junit_artifact(repository, baseline_revision,
                                          baseline_run_id, **kwargs)
    after = verify_actions_junit_artifact(repository, candidate_revision,
                                         candidate_run_id, **kwargs)
    return compare_actions_junit_replays(before, after)


__all__ = ["ActionsReadSource", "GitHubActionsRestReader", "ActionsArtifactReceipt",
           "ActionsReplayGate", "verify_actions_junit_artifact", "compare_actions_junit_replays", "audit_actions_replay"]
