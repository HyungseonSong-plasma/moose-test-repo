"""Acquire a bounded Actions artifact and bind it to generated HIT facts.

GitHub metadata witnesses archive custody, not arbitrary generator execution.
A manifest inside the archive is a producer assertion, not an attestation.
The artifact ID is assigned after upload and is obtained from API metadata,
never demanded in the pre-upload manifest.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import inspect
import json
from pathlib import Path
import re
import sys
from time import monotonic
from types import CodeType, FunctionType

from ..diagnostics.collector import CollectionResult
from ..diagnostics.providers.generated_input import (
    GeneratedInputIdentity, collect_generated_input,
)
from ..diagnostics.providers.git import GitSourceProvider
from ..diagnostics.request import ScanRequest, normalized_path
from libs.git_evidence import (
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
        if not isinstance(run, dict) or not isinstance(run.get("repository"), dict):
            raise ValueError("GENERATED_ACTIONS_RUN_INVALID")
        repository = run["repository"]
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
        owner = item.get("workflow_run")
        if not isinstance(owner, dict):
            raise ValueError("GENERATED_ARTIFACT_ASSOCIATION_MISMATCH")
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
    manifest_identity = dict(manifest["identity"])
    expected_manifest = asdict(expected)
    expected_manifest.pop("artifact_id")
    if manifest_identity != expected_manifest or set(manifest_identity) != set(expected_manifest):
        raise ValueError("GENERATED_RECEIPT_IDENTITY_MISMATCH")
    receipt = GeneratedInputIdentity(
        **manifest_identity, artifact_id=expected.artifact_id)
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


@dataclass(frozen=True, slots=True)
class GeneratedCapture:
    """Locally observed return bytes and pre-upload producer assertion.

    Not an authenticated runner/job/Artifact receipt. No output is written
    to the checkout and no upload or Native execution is performed.
    """
    function_name: str
    hit: bytes
    manifest: bytes

    @property
    def producer_authenticated(self) -> bool:
        return False


def verify_loaded_python_function(request: ScanRequest, provider: GitSourceProvider,
                                  producer_path: str, producer_blob_sha: str, function):
    """Check an explicitly loaded top-level callable against exact tracked source.

    Compile for code-object comparison only; never import or execute source.
    This does not attest globals, dependencies or runner identity.
    """
    if (type(function) is not FunctionType or function.__qualname__ != function.__name__
            or function.__closure__ is not None or inspect.iscoroutinefunction(function)
            or inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function)):
        raise ValueError("GENERATED_CAPTURE_FUNCTION_UNSUPPORTED")
    if not producer_path.endswith(".py") or not request.selects(producer_path):
        raise ValueError("GENERATED_CAPTURE_PATH_INVALID")
    provider.assert_head(request.revision)
    source = provider.read_at_revision(request.revision, producer_path)
    if source.record.blob_sha != producer_blob_sha:
        raise ValueError("GENERATED_PRODUCER_BLOB_MISMATCH")
    if len(source.content) > request.budget.max_bytes:
        raise ValueError("GENERATED_CAPTURE_SOURCE_BYTE_BUDGET")
    filename = Path(function.__code__.co_filename)
    expected_file = provider.root.resolve() / producer_path
    if (filename.resolve() != expected_file or expected_file.is_symlink()
            or expected_file.resolve() != expected_file):
        raise ValueError("GENERATED_CAPTURE_FUNCTION_SOURCE_MISMATCH")
    module_path = function.__globals__.get("__file__")
    if not isinstance(module_path, str) or Path(module_path).resolve() != expected_file:
        raise ValueError("GENERATED_CAPTURE_FUNCTION_SOURCE_MISMATCH")
    with expected_file.open("rb") as stream:
        actual = stream.read(request.budget.max_bytes + 1)
    if actual != source.content:
        raise ValueError("GENERATED_CAPTURE_WORKTREE_SOURCE_MISMATCH")
    # Compile only (never exec): compare the loaded top-level code object
    # against the exact Git source, including constants and nested code.
    compiled = compile(source.content, function.__code__.co_filename, "exec",
                       dont_inherit=True, optimize=sys.flags.optimize)
    matches = [obj for obj in compiled.co_consts
               if isinstance(obj, CodeType) and obj.co_name == function.__name__]
    if len(matches) != 1 or matches[0] != function.__code__:
        raise ValueError("GENERATED_CAPTURE_CODE_MISMATCH")

    return source


def capture_generated_return(
    request: ScanRequest, provider: GitSourceProvider, *,
    producer_path: str, producer_blob_sha: str, function, arguments: dict,
    artifact_path: str, run_id: int, attempt: int, job_id: int,
    workflow_path: str,
) -> GeneratedCapture:
    """Explicitly invoke one vetted, top-level Python text-returning function.

    Only use with a trusted, owner-authorized callable already loaded in the
    current interpreter. This is not a sandbox, arbitrary-module loader,
    process runner, tracer or dependency-closure proof. The time budget is a
    post-call acceptance bound, not a preemptive timeout. No arbitrary code
    is imported or executed by source scanning. Inputs are limited to small,
    finite JSON scalars; only their digest (not values) enters the manifest.
    Do not pass secrets. Globals/imports/default configuration, runner and
    GitHub job/upload ownership are not attested.
    """
    started = monotonic()
    if not isinstance(request, ScanRequest) or not isinstance(provider, GitSourceProvider):
        raise TypeError("GENERATED_CAPTURE_SOURCE_REQUIRED")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", request.repository):
        raise ValueError("GENERATED_REPOSITORY_INVALID")
    for path in (producer_path, artifact_path, workflow_path):
        normalized_path(path)
    if (not producer_path.endswith(".py") or not request.selects(producer_path)
            or not artifact_path.endswith(".i")
            or not re.fullmatch(r"[A-Za-z0-9_.+/-]+", artifact_path)
            or not workflow_path.startswith(".github/workflows/")
            or not workflow_path.endswith((".yml", ".yaml"))):
        raise ValueError("GENERATED_CAPTURE_PATH_INVALID")
    if any(type(value) is not int or value < 1 for value in (run_id, attempt, job_id)):
        raise ValueError("GENERATED_CAPTURE_CONTEXT_INVALID")
    if type(function) is not FunctionType or function.__qualname__ != function.__name__:
        raise TypeError("GENERATED_CAPTURE_TOP_LEVEL_FUNCTION_REQUIRED")
    if function.__closure__ is not None or inspect.iscoroutinefunction(function) or inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function):
        raise ValueError("GENERATED_CAPTURE_FUNCTION_UNSUPPORTED")
    if type(arguments) is not dict or any(type(k) is not str for k in arguments):
        raise TypeError("GENERATED_CAPTURE_ARGUMENTS_REQUIRED")
    signature = inspect.signature(function, follow_wrapped=False)
    if any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in signature.parameters.values()):
        raise ValueError("GENERATED_CAPTURE_VARIADIC_UNSUPPORTED")
    bound = signature.bind(**arguments)
    bound.apply_defaults()
    if len(bound.arguments) > 32:
        raise ValueError("GENERATED_CAPTURE_ARGUMENT_LIMIT")
    for value in bound.arguments.values():
        if type(value) not in (type(None), bool, int, float, str):
            raise ValueError("GENERATED_CAPTURE_ARGUMENT_UNSUPPORTED")
        if type(value) is str and len(value) > 4096:
            raise ValueError("GENERATED_CAPTURE_ARGUMENT_LIMIT")
        if type(value) is int and value.bit_length() > 256:
            raise ValueError("GENERATED_CAPTURE_ARGUMENT_LIMIT")
    invocation = json.dumps(
        {"function": function.__name__, "arguments": dict(bound.arguments)},
        sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":")).encode("ascii")
    if len(invocation) > min(64_000, request.budget.max_bytes):
        raise ValueError("GENERATED_CAPTURE_ARGUMENT_LIMIT")
    invocation_digest = sha256(invocation).hexdigest()


    def time_check():
        if monotonic() - started > request.budget.max_seconds:
            raise ValueError("GENERATED_CAPTURE_TIME_BUDGET_EXCEEDED")

    verify_loaded_python_function(request, provider, producer_path, producer_blob_sha, function)
    time_check()
    returned = function(*bound.args, **bound.kwargs)
    time_check()
    if type(returned) is not str:
        raise TypeError("GENERATED_CAPTURE_TEXT_RETURN_REQUIRED")
    if len(returned) > request.budget.max_bytes:
        raise ValueError("GENERATED_CAPTURE_OUTPUT_BYTE_BUDGET")
    hit = returned.encode("utf-8", "strict")
    if not hit or len(hit) > request.budget.max_bytes:
        raise ValueError("GENERATED_CAPTURE_OUTPUT_BYTE_BUDGET")
    verify_loaded_python_function(request, provider, producer_path, producer_blob_sha, function)
    time_check()
    identity = {
        "repository": request.repository, "source_sha": request.revision,
        "producer_path": producer_path, "producer_blob_sha": producer_blob_sha,
        "run_id": run_id, "attempt": attempt, "artifact_path": artifact_path,
        "artifact_sha256": sha256(hit).hexdigest(),
        "invocation_sha256": invocation_digest,
    }
    manifest = json.dumps(
        {"schema_version": 1, "identity": identity, "job_id": job_id,
         "workflow_path": workflow_path},
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    return GeneratedCapture(function.__name__, hit, manifest)


__all__ = ["GeneratedActionsReceipt", "acquire_generated_input",
           "GeneratedCapture", "capture_generated_return"]
