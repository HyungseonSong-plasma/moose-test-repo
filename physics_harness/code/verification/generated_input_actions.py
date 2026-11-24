"""Acquire a bounded Actions artifact and bind it to generated HIT facts.

GitHub metadata witnesses archive custody, not arbitrary generator execution.
A manifest inside the archive is a producer assertion, not an attestation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from time import monotonic

from ..diagnostics.collector import CollectionResult
from ..diagnostics.providers.generated_input import (
    GeneratedInputIdentity, collect_generated_input,
)
from ..diagnostics.providers.git import GitSourceProvider
from ..diagnostics.request import ScanRequest, normalized_path
from .naming_actions import (
    ActionsReadSource, GitHubActionsRestReader, read_actions_archive_members,
)


@dataclass(frozen=True, slots=True)
class GeneratedActionsReceipt:
    identity: GeneratedInputIdentity
    workflow_path: str
    job_id: int
    artifact_name: str
    archive_sha256: str
    manifest_sha256: str
    source: str
    result: CollectionResult
    unresolved: tuple[str, ...]

    @property
    def producer_authenticated(self) -> bool:
        return False


def _strict_json(data: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("GENERATED_MANIFEST_DUPLICATE_KEY")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("GENERATED_MANIFEST_NONSTANDARD_JSON")

    value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=pairs,
                       parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError("GENERATED_MANIFEST_INVALID")
    return value


def acquire_generated_input(
    request: ScanRequest, provider: GitSourceProvider, *,
    expected: GeneratedInputIdentity, workflow_path: str, job_id: int,
    artifact_name: str, manifest_path: str, expected_archive_sha256: str,
    required_step_names: tuple[str, ...], source: ActionsReadSource | None = None,
) -> GeneratedActionsReceipt:
    """Read actual archive bytes via the existing read-only Actions reader.

    First-attempt successful runs only: GitHub artifact metadata identifies
    the run, not the upload attempt. Later attempts require a separate trusted
    attempt-binding mechanism. The independently selected identity must match
    the manifest and both digests; job/step success does not prove causality.
    No workflow is launched. Errors fail closed without returning graph facts.
    """
    started = monotonic()
    if not isinstance(expected, GeneratedInputIdentity):
        raise TypeError("GENERATED_IDENTITY_REQUIRED")
    if expected.repository != request.repository or expected.source_sha != request.revision:
        raise ValueError("GENERATED_SOURCE_SCOPE_MISMATCH")
    if expected.attempt != 1:
        raise ValueError("ARTIFACT_ATTEMPT_BINDING_UNPROVEN")
    if not request.selects(expected.producer_path):
        raise ValueError("GENERATED_PRODUCER_OUT_OF_SCOPE")
    normalized_path(workflow_path)
    normalized_path(manifest_path)
    if (not workflow_path.startswith(".github/workflows/")
            or not workflow_path.endswith((".yml", ".yaml"))
            or not manifest_path.endswith(".json")
            or manifest_path == expected.artifact_path):
        raise ValueError("GENERATED_ACTIONS_SELECTOR_INVALID")
    if (type(job_id) is not int or job_id < 1
            or not isinstance(artifact_name, str) or not artifact_name.strip()
            or not isinstance(expected_archive_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_archive_sha256)
            or not isinstance(required_step_names, tuple) or not required_step_names
            or any(not isinstance(s, str) or not s.strip() for s in required_step_names)
            or len(set(required_step_names)) != len(required_step_names)):
        raise ValueError("GENERATED_ACTIONS_SELECTOR_INVALID")
    # Check exact source before downloading any artifact.
    producer = provider.read_at_revision(request.revision, expected.producer_path)
    if producer.record.blob_sha != expected.producer_blob_sha:
        raise ValueError("GENERATED_PRODUCER_BLOB_MISMATCH")
    reader = source if source is not None else GitHubActionsRestReader()
    source_kind = ("GITHUB_REST_HTTPS" if type(reader) is GitHubActionsRestReader
                   else "INJECTED_READER")
    repo, run_id = expected.repository, expected.run_id

    def time_check():
        if monotonic() - started > request.budget.max_seconds:
            raise ValueError("GENERATED_ACQUISITION_TIME_BUDGET_EXCEEDED")

    def run_identity():
        time_check()
        run = reader.run(repo, run_id)
        time_check()
        repository = run.get("repository") or {}
        if (type(repository.get("id")) is not int or repository["id"] < 1
                or repository.get("full_name") != repo
                or run.get("id") != run_id
                or run.get("head_sha") != request.revision
                or run.get("run_attempt") != expected.attempt
                or run.get("path") != workflow_path
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
                or not isinstance(run.get("updated_at"), str)
                or not run["updated_at"]):
            raise ValueError("GENERATED_ACTIONS_RUN_MISMATCH")
        return (repository["id"], run["updated_at"])

    def artifact_identity(repo_id):
        time_check()
        items = reader.artifacts(repo, run_id)
        time_check()
        if not isinstance(items, list) or any(not isinstance(a, dict) for a in items):
            raise ValueError("GENERATED_ARTIFACT_LIST_INVALID")
        selected = [a for a in items if a.get("id") == expected.artifact_id
                    or a.get("name") == artifact_name]
        if len(selected) != 1:
            raise ValueError("GENERATED_ARTIFACT_MISSING_OR_AMBIGUOUS")
        item = selected[0]
        owner = item.get("workflow_run") or {}
        if (item.get("id") != expected.artifact_id
                or item.get("name") != artifact_name
                or item.get("expired") is not False
                or owner.get("id") != run_id
                or owner.get("head_sha") != request.revision
                or owner.get("repository_id") != repo_id
                or item.get("digest") != "sha256:" + expected_archive_sha256):
            raise ValueError("GENERATED_ARTIFACT_ASSOCIATION_MISMATCH")
        return (item["id"], item["name"], item["digest"])

    before = run_identity()
    jobs = reader.jobs(repo, run_id)
    time_check()
    if not isinstance(jobs, list) or any(not isinstance(j, dict) for j in jobs):
        raise ValueError("GENERATED_JOB_LIST_INVALID")
    selected = [j for j in jobs if j.get("id") == job_id]
    if len(selected) != 1:
        raise ValueError("GENERATED_JOB_MISSING_OR_AMBIGUOUS")
    job = selected[0]
    if (job.get("run_id") != run_id or job.get("head_sha") != request.revision
            or job.get("run_attempt") != expected.attempt
            or job.get("status") != "completed" or job.get("conclusion") != "success"):
        raise ValueError("GENERATED_JOB_ASSOCIATION_MISMATCH")
    steps = job.get("steps")
    if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
        raise ValueError("GENERATED_JOB_STEPS_INVALID")
    for name in required_step_names:
        matching = [s for s in steps if s.get("name") == name]
        if (len(matching) != 1 or matching[0].get("status") != "completed"
                or matching[0].get("conclusion") != "success"):
            raise ValueError("GENERATED_REQUIRED_STEP_NOT_PASSED:" + name)

    artifact = artifact_identity(before[0])
    archive = reader.archive(repo, expected.artifact_id)
    time_check()
    if not isinstance(archive, bytes) or len(archive) > min(
            20_000_000, request.budget.max_bytes):
        raise ValueError("GENERATED_ARCHIVE_BYTE_BUDGET_EXCEEDED")
    if sha256(archive).hexdigest() != expected_archive_sha256:
        raise ValueError("GENERATED_ARCHIVE_DIGEST_MISMATCH")
    members = read_actions_archive_members(
        archive, entries=(expected.artifact_path, manifest_path),
        max_member_bytes=min(8_000_000, request.budget.max_bytes),
        max_total_bytes=min(20_000_000, request.budget.max_bytes))
    time_check()
    manifest_bytes = members[manifest_path]
    if len(manifest_bytes) > 64_000:
        raise ValueError("GENERATED_MANIFEST_SIZE_LIMIT")
    manifest = _strict_json(manifest_bytes)
    if set(manifest) != {"schema_version", "identity", "job_id", "workflow_path"}:
        raise ValueError("GENERATED_MANIFEST_FIELDS_INVALID")
    if (type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or type(manifest["job_id"]) is not int or manifest["job_id"] != job_id
            or manifest["workflow_path"] != workflow_path
            or not isinstance(manifest["identity"], dict)):
        raise ValueError("GENERATED_MANIFEST_CONTEXT_MISMATCH")
    receipt = GeneratedInputIdentity(**manifest["identity"])
    if receipt != expected:
        raise ValueError("GENERATED_RECEIPT_IDENTITY_MISMATCH")
    if artifact_identity(before[0]) != artifact or run_identity() != before:
        raise ValueError("GENERATED_ACTIONS_CHANGED_DURING_READ")
    result = collect_generated_input(
        request, provider, expected=expected, receipt=receipt,
        content=members[expected.artifact_path])
    time_check()
    unresolved = set(result.batch.unresolved)
    unresolved.update((
        "ARTIFACT_PRODUCING_JOB_NOT_ATTESTED",
        "GENERATOR_INVOCATION_CAUSAL_BINDING_UNVERIFIED",
        "RUNNER_AND_WORKFLOW_EXECUTION_NOT_ATTESTED",
    ))
    if source_kind == "INJECTED_READER":
        unresolved.add("INJECTED_SOURCE_NOT_GITHUB_AUTHENTICATION")
    return GeneratedActionsReceipt(
        expected, workflow_path, job_id, artifact_name,
        expected_archive_sha256, sha256(manifest_bytes).hexdigest(),
        source_kind, result, tuple(sorted(unresolved)))


__all__ = ["GeneratedActionsReceipt", "acquire_generated_input"]
