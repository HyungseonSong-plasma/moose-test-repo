"""PR-scoped append-only state planning; no Git or GitHub write authority.

A trusted caller binds the actual PR and exact head, supplies the pinned Samuel
codec, and publishes one non-force child commit containing the record. State
belongs to the PR, not to a shared Issue comment. No migration or enrollment.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from collections.abc import Callable, Iterable

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_BRANCH = re.compile(r"issue-[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_MAX_BODY = 240_000
_MAX_RECORD = 1_000_000


class PRStateHold(ValueError):
    """Scope, state or head evidence cannot authorize a candidate."""


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


@dataclass(frozen=True, slots=True)
class PRBinding:
    repository: str
    pr_number: int
    branch: str
    work_id: str

    def __post_init__(self):
        if (not isinstance(self.repository, str) or not _REPO.fullmatch(self.repository)
                or type(self.pr_number) is not int or self.pr_number <= 0
                or not isinstance(self.branch, str) or not _BRANCH.fullmatch(self.branch)
                or ".." in self.branch or self.branch.endswith((".", ".lock"))
                or not isinstance(self.work_id, str) or not self.work_id.strip()
                or len(self.work_id) > 512):
            raise PRStateHold("INVALID_PR_BINDING")

    @property
    def prefix(self) -> str:
        return f"automation/controller-state/pr-{self.pr_number}/"


def validate_bindings(bindings: Iterable[PRBinding]) -> tuple[PRBinding, ...]:
    """Reject shared branch ownership and duplicate PR identities per repo.

    Different PRs may have the same work ID, but are independent candidates,
    not independent authority to execute the same external operation.
    """
    result = tuple(bindings)
    if not result or any(not isinstance(x, PRBinding) for x in result):
        raise PRStateHold("INVALID_BINDING_INVENTORY")
    if (len({(x.repository.lower(), x.pr_number) for x in result}) != len(result)
            or len({(x.repository.lower(), x.branch) for x in result}) != len(result)):
        raise PRStateHold("SHARED_PR_OR_BRANCH")
    return result


@dataclass(frozen=True, slots=True)
class PRStateSnapshot:
    binding: PRBinding
    head: str
    revision: int
    body: str
    record_sha256: str


@dataclass(frozen=True, slots=True)
class PRStatePlan:
    binding: PRBinding
    expected_head: str
    revision: int
    path: str
    record: bytes
    record_sha256: str

    @property
    def write_authorized(self) -> bool:
        return False


def _decode(body: str, binding: PRBinding, revision: int, decode_state: Callable):
    if (not isinstance(body, str) or len(body.encode("utf-8")) > _MAX_BODY
            or not body.startswith("<!-- samuel-controller-state -->\n")):
        raise PRStateHold("INVALID_STATE_BODY")
    try:
        state = decode_state(body)
        if (state.research_id != binding.work_id or type(state.revision) is not int
                or state.revision != revision):
            raise PRStateHold("STATE_IDENTITY_MISMATCH")
        return state
    except PRStateHold:
        raise
    except Exception as exc:
        raise PRStateHold("STATE_DECODE_FAILED") from exc


def plan_pr_state(*, binding: PRBinding, base: PRStateSnapshot, proposed,
                  encode_state: Callable, decode_state: Callable,
                  require_fresh_write: Callable) -> PRStatePlan:
    """Plan a single immutable revision record on the enrolled work branch.

    Snapshot must come from an independently verified chain at exact PR HEAD;
    this function is not a ledger reader or proof of enrollment. The runtime
    must check path absence and commit only this file, with expected HEAD as
    the sole parent and a non-force update. A stale head requires fresh review.
    """
    if (not isinstance(binding, PRBinding) or not isinstance(base, PRStateSnapshot)
            or base.binding != binding or not isinstance(base.head, str)
            or not _SHA.fullmatch(base.head) or type(base.revision) is not int
            or not 0 <= base.revision < 10**16 - 1
            or not isinstance(base.record_sha256, str) or not _DIGEST.fullmatch(base.record_sha256)
            or not all(callable(x) for x in (encode_state, decode_state, require_fresh_write))):
        raise PRStateHold("INVALID_PR_SNAPSHOT")
    old = _decode(base.body, binding, base.revision, decode_state)
    try:
        if (proposed.research_id != binding.work_id or type(proposed.revision) is not int
                or proposed.revision != base.revision + 1):
            raise PRStateHold("INVALID_NEXT_REVISION")
        require_fresh_write(old, proposed)
        body = encode_state(proposed)
        decoded = _decode(body, binding, proposed.revision, decode_state)
        if decoded != proposed:
            raise PRStateHold("STATE_ROUNDTRIP_MISMATCH")
    except PRStateHold:
        raise
    except Exception as exc:
        raise PRStateHold("SAMUEL_VALIDATION_FAILED") from exc
    record = _canonical({"schema_version": 1, "repository": binding.repository,
                         "pr_number": binding.pr_number, "branch": binding.branch,
                         "work_id": binding.work_id, "revision": proposed.revision,
                         "expected_parent": base.head, "previous_record_sha256": base.record_sha256,
                         "state_body": body, "state_body_sha256": _digest(body.encode("utf-8"))})
    if len(record) > _MAX_RECORD:
        raise PRStateHold("RECORD_LIMIT")
    return PRStatePlan(binding, base.head, proposed.revision,
                       binding.prefix + f"r{proposed.revision:016d}.json", record, _digest(record))


def classify_publication(plan: PRStatePlan, *, binding: PRBinding, current_head: str,
                         record_at_path: bytes | None, verified_record_commit: bool = False) -> str:
    """Classify fresh exact-head observations; never authorize a retry.

    verified_record_commit means trusted history evidence established that the
    exact planned bytes were added in a single-parent commit from expected_head,
    with only plan.path changed, and that commit is an ancestor of current HEAD.
    A byte match alone is insufficient. A missing record at a changed head is
    always stale, not a reason to replay or overwrite.
    """
    if (not isinstance(plan, PRStatePlan) or binding != plan.binding
            or not isinstance(current_head, str) or not _SHA.fullmatch(current_head)
            or type(verified_record_commit) is not bool
            or (record_at_path is not None and not isinstance(record_at_path, bytes))):
        return "HOLD_IDENTITY_OR_EVIDENCE"
    if record_at_path is not None:
        if record_at_path != plan.record:
            return "HOLD_RECORD_CONFLICT"
        if not verified_record_commit or current_head == plan.expected_head:
            return "HOLD_UNVERIFIED_PUBLICATION"
        return "RECORD_OBSERVED"
    return "READY_FOR_REVIEW" if current_head == plan.expected_head else "HOLD_STALE_HEAD"
