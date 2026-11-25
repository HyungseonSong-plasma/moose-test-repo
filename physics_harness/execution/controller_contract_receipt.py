"""MOOSE-specific verification of Samuel-correlated qualification evidence.

All observations and expected hashes must come from authenticated runtime ports.
No network access, dispatch implementation, mutation authority or live CAS claim.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from types import MappingProxyType
from collections.abc import Mapping

REPO = "HyungseonSong-plasma/moose-test-repo"
WORKFLOW = ".github/workflows/controller-checkpoint-contract.yml"
CONTRACT = "automation/controller/checkpoint-write-contract.json"
SOURCE_PATHS = frozenset((CONTRACT, WORKFLOW,
    "automation/controller/qualify_checkpoint_contract.py",
    "docs/operating_system/central_skills.json",
    "physics_harness/code/tests/test_checkpoint_cas_contract.py",
    "physics_harness/code/tests/test_checkpoint_contract_receipt.py",
    "physics_harness/execution/controller_contract_receipt.py",
    "physics_harness/code/tests/test_controller_contract_receipt.py"))
TESTS = frozenset(("test_exact_parent_single_path", "test_independent_pr_parallel",
    "test_same_pr_race_exactly_one_wins", "test_intervening_code_commit_is_preserved",
    "test_lost_response_requires_readback_not_replay", "test_record_cannot_be_overwritten",
    "test_unexpected_parent_rejected"))
_SHA = re.compile(r"[a-f0-9]{40}\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
MAX_BYTES = 1_000_000


def _check(condition, reason):
    if not condition:
        raise ValueError(reason)


def _valid(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _positive(value):
    return type(value) is int and value > 0


def _unique_pairs(items):
    result = {}
    for key, value in items:
        _check(key not in result, "DUPLICATE_RECEIPT_FIELD")
        result[key] = value
    return result


@dataclass(frozen=True)
class ContractRequest:
    source_sha: str
    samuel_pin: str
    source_hashes: Mapping[str, str]
    correlation_id: str

    def __post_init__(self):
        object.__setattr__(self, "source_hashes", MappingProxyType(dict(self.source_hashes)))

    def dispatch_kwargs(self):
        _check(_valid(_SHA, self.source_sha) and _valid(_SHA, self.samuel_pin)
               and _valid(_ID, self.correlation_id) and set(self.source_hashes) == SOURCE_PATHS
               and all(_valid(_HASH, x) for x in self.source_hashes.values()), "INVALID_CONTRACT_REQUEST")
        return dict(workflow=WORKFLOW.rsplit("/", 1)[-1], ref="main",
                    correlation_id=self.correlation_id,
                    correlation_run_name_prefix="checkpoint-contract:",
                    correlation_input="correlation_id", inputs={
                        "expected_main_sha": self.source_sha,
                        "expected_contract_sha256": self.source_hashes[CONTRACT],
                        "expected_samuel_pin": self.samuel_pin})


@dataclass(frozen=True)
class QualifiedContract:
    source_sha: str
    samuel_pin: str
    source_hashes: tuple[tuple[str, str], ...]
    run_id: int
    run_attempt: int
    artifact_id: int
    artifact_sha256: str
    correlation_id: str

    @property
    def write_authorized(self):
        return False

    @property
    def live_connector_qualified(self):
        return False


def verify_receipt(request: ContractRequest, *, correlation_status: str,
                   matched_run_id: int, run: dict, job: dict, artifact: dict,
                   archive: bytes) -> QualifiedContract:
    """Consume Samuel MATCHED_TERMINAL plus fresh authenticated REST metadata.

    The runtime must resolve exactly one matching job and artifact for this run
    attempt with complete enumeration and download the exact artifact ID.
    No caller-provided evidence can independently establish its own provenance.
    """
    request.dispatch_kwargs()
    _check(correlation_status == "MATCHED_TERMINAL" and _positive(matched_run_id), "RUN_NOT_CORRELATED")
    attempt = run.get("run_attempt")
    _check(_positive(attempt) and run.get("id") == matched_run_id
           and run.get("repository", {}).get("full_name") == REPO
           and run.get("head_repository", {}).get("full_name") == REPO
           and run.get("path") == WORKFLOW and run.get("event") == "workflow_dispatch"
           and run.get("head_branch") == "main" and run.get("head_sha") == request.source_sha
           and run.get("display_title") == "checkpoint-contract:" + request.correlation_id
           and run.get("status") == "completed" and run.get("conclusion") == "success", "RUN_IDENTITY_OR_RESULT_MISMATCH")
    _check(_positive(job.get("id")) and job.get("run_id") == matched_run_id
           and job.get("run_attempt") == attempt and job.get("head_sha") == request.source_sha
           and job.get("name") == "qualify" and job.get("status") == "completed"
           and job.get("conclusion") == "success", "JOB_NOT_QUALIFIED")
    _check(_positive(artifact.get("id")) and artifact.get("name") == f"checkpoint-contract-{matched_run_id}-{attempt}"
           and artifact.get("expired") is False and artifact.get("workflow_run", {}).get("id") == matched_run_id
           and artifact.get("workflow_run", {}).get("head_sha") == request.source_sha, "ARTIFACT_IDENTITY_MISMATCH")
    _check(type(archive) is bytes and 0 < len(archive) <= MAX_BYTES
           and artifact.get("size_in_bytes") == len(archive)
           and artifact.get("digest") == "sha256:" + sha256(archive).hexdigest(), "ARTIFACT_DIGEST_MISMATCH")
    with ZipFile(BytesIO(archive)) as z:
        names = {"checkpoint-contract-receipt.json", "checkpoint-cas.xml"}
        infos = z.infolist()
        _check(len(infos) == 2 and {i.filename for i in infos} == names
               and all(0 < i.file_size <= MAX_BYTES and not i.is_dir() for i in infos), "ARTIFACT_CONTENT_MISMATCH")
        receipt = json.loads(z.read("checkpoint-contract-receipt.json"), object_pairs_hook=_unique_pairs)
        junit = z.read("checkpoint-cas.xml")
    expected = dict(schema_version=1, repository=REPO, source_sha=request.source_sha,
                    samuel_pin=request.samuel_pin, source_sha256=dict(request.source_hashes),
                    run_id=str(matched_run_id), run_attempt=str(attempt),
                    correlation_id=request.correlation_id, tests_passed=sorted(TESTS),
                    junit_sha256=sha256(junit).hexdigest(), status="LOCAL_GIT_CONTRACT_QUALIFIED",
                    live_connector_qualified=False, write_authorized=False)
    _check(type(receipt) is dict and receipt == expected and type(receipt["schema_version"]) is int
           and receipt["write_authorized"] is False and receipt["live_connector_qualified"] is False, "RECEIPT_MISMATCH")
    _check(b"<!" not in junit, "UNSAFE_JUNIT")
    cases = list(ET.fromstring(junit).iter("testcase"))
    _check(len(cases) == len(TESTS) and {c.get("name") for c in cases} == TESTS
           and all(not any(c.find(t) is not None for t in ("failure", "error", "skipped")) for c in cases), "JUNIT_NOT_QUALIFIED")
    return QualifiedContract(request.source_sha, request.samuel_pin, tuple(sorted(request.source_hashes.items())),
                             matched_run_id, attempt, artifact["id"], sha256(archive).hexdigest(), request.correlation_id)


def dispatch_contract(request, transport, *, samuel_runtime=None):
    """Use pinned Samuel dispatch_workflow; caller owns authorization and transport.

    Persist returned dispatch receipt before observing it. Never dispatch again
    merely because observation is pending. Default import is the existing Samuel
    API, not a local reimplementation. Runtime must verify the installed pin.
    """
    if samuel_runtime is None:
        from chatgpt_operation.github import actions_runtime as samuel_runtime
    return samuel_runtime.dispatch_workflow(transport, **request.dispatch_kwargs())


def observe_contract(request, transport, dispatch_receipt, *, samuel_runtime=None):
    """Observe once through Samuel; caller fetches matched run/job/artifact.

    Require the persisted, authenticated dispatch receipt for this request. The
    returned result is not itself a qualification receipt or write authority.
    """
    request.dispatch_kwargs()
    _check(dispatch_receipt.get("workflow_path") == WORKFLOW
           and dispatch_receipt.get("ref") == "main"
           and dispatch_receipt.get("correlation_id") == request.correlation_id
           and dispatch_receipt.get("correlation_input") == "correlation_id"
           and dispatch_receipt.get("correlation_run_name_prefix") == "checkpoint-contract:",
           "DISPATCH_RECEIPT_MISMATCH")
    if samuel_runtime is None:
        from chatgpt_operation.github import actions_runtime as samuel_runtime
    return samuel_runtime.observe_dispatch_once(transport, dispatch_receipt,
                                                expected_head_sha=request.source_sha)
