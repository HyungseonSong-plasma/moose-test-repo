"""Read-only Controller state adapter for a trusted, dedicated Issue ledger.

The runtime owns the Issue binding, read transport and pinned Samuel decoder.
This module does not write, enroll work, grant execution authority or supply an
independent blocker-journal anchor. Stable reads are not atomic snapshots.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Any

STATE_MARKER = "<!-- samuel-controller-state -->"
_PAGE_SIZE = 100
_MAX_PAGES = 100
_MAX_BODY_BYTES = 240_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class DurableReadError(ValueError):
    """Missing, ambiguous, stale or untrusted state; stop the affected path."""


@dataclass(frozen=True, slots=True)
class StateBinding:
    repository: str
    issue_number: int
    issue_id: int
    actor_id: int
    research_id: str
    minimum_revision: int

    def __post_init__(self):
        if (not isinstance(self.repository, str) or not _REPO.fullmatch(self.repository)
                or any(type(n) is not int or n <= 0 for n in
                       (self.issue_number, self.issue_id, self.actor_id))
                or not isinstance(self.research_id, str) or not self.research_id.strip()
                or type(self.minimum_revision) is not int or self.minimum_revision < 0):
            raise DurableReadError("INVALID_STATE_BINDING")


@dataclass(frozen=True, slots=True)
class StateRead:
    binding: StateBinding
    comment_id: int
    revision: int
    body_sha256: str
    state: Any  # Pinned Samuel ResearchState; runtime must treat as read-only.

    @property
    def evidence_ref(self) -> str:
        return (f"https://github.com/{self.binding.repository}/issues/"
                f"{self.binding.issue_number}#issuecomment-{self.comment_id}"
                f"@revision:{self.revision}:sha256:{self.body_sha256}")


@dataclass(frozen=True, slots=True)
class Reconciliation:
    status: str
    reasons: tuple[str, ...]
    evidence_ref: str

    @property
    def execution_authorized(self) -> bool:
        return False


def _inventory(binding: StateBinding, read_issue, read_comments):
    """Read all pages, with bounded count and duplicate-ID checks."""
    def issue_count():
        issue = read_issue(binding.repository, binding.issue_number)
        if (not isinstance(issue, Mapping) or type(issue.get("id")) is not int
                or issue["id"] != binding.issue_id or issue.get("number") != binding.issue_number
                or issue.get("url") != f"https://api.github.com/repos/{binding.repository}/issues/{binding.issue_number}"
                or "pull_request" in issue or type(issue.get("comments")) is not int
                or not 0 <= issue["comments"] < _MAX_PAGES * _PAGE_SIZE):
            raise DurableReadError("ISSUE_IDENTITY_OR_COUNT_INVALID")
        return issue["comments"]

    count = issue_count()
    seen = set()
    fingerprints = []
    candidates = []
    for page in range(1, _MAX_PAGES + 1):
        rows = read_comments(binding.repository, binding.issue_number, page, _PAGE_SIZE)
        if not isinstance(rows, list) or len(rows) > _PAGE_SIZE:
            raise DurableReadError("COMMENT_PAGE_INVALID")
        for item in rows:
            if not isinstance(item, Mapping):
                raise DurableReadError("COMMENT_INVALID")
            cid, body, actor = item.get("id"), item.get("body"), item.get("user")
            if (type(cid) is not int or cid <= 0 or cid in seen
                    or not isinstance(body, str) or not isinstance(actor, Mapping)
                    or type(actor.get("id")) is not int or actor["id"] <= 0
                    or not isinstance(item.get("updated_at"), str) or not item["updated_at"]
                    or item.get("issue_url") != f"https://api.github.com/repos/{binding.repository}/issues/{binding.issue_number}"):
                raise DurableReadError("COMMENT_IDENTITY_INVALID")
            seen.add(cid)
            body_bytes = body.encode("utf-8")
            if len(body_bytes) > _MAX_BODY_BYTES:
                raise DurableReadError("COMMENT_BODY_LIMIT")
            fingerprint = (cid, actor["id"], item["updated_at"], sha256(body_bytes).hexdigest())
            fingerprints.append(fingerprint)
            if STATE_MARKER in body:
                candidates.append((fingerprint, body))
        if len(rows) < _PAGE_SIZE:
            break
    else:
        raise DurableReadError("COMMENT_ENUMERATION_LIMIT")
    if len(seen) != count or issue_count() != count:
        raise DurableReadError("COMMENT_ENUMERATION_INCOMPLETE")
    return tuple(fingerprints), tuple(candidates)


def load_state(*, binding: StateBinding, read_issue: Callable, read_comments: Callable,
               decode_state: Callable[[str], Any]) -> StateRead:
    """Bind a stable ledger read to trusted identity, then use Samuel's decoder.

    Missing state never means a new task. An explicit separate enrollment is
    required. The trusted runtime must supply the decoder from its verified pin
    and a read-only transport; neither is chosen from Issue contents.
    """
    if not isinstance(binding, StateBinding) or not all(callable(p) for p in
            (read_issue, read_comments, decode_state)):
        raise DurableReadError("TRUSTED_STATE_PORTS_REQUIRED")
    try:
        first = _inventory(binding, read_issue, read_comments)
        second = _inventory(binding, read_issue, read_comments)
    except DurableReadError:
        raise
    except Exception as exc:
        raise DurableReadError("STATE_READ_UNAVAILABLE") from exc
    if first != second:
        raise DurableReadError("STATE_LEDGER_CHANGED")
    candidates = second[1]
    if not candidates:
        raise DurableReadError("STATE_MISSING_NOT_ENROLLMENT")
    if len(candidates) != 1:
        raise DurableReadError("AMBIGUOUS_STATE_COMMENT")
    fingerprint, body = candidates[0]
    comment_id, actor_id, _, body_digest = fingerprint
    if actor_id != binding.actor_id or not body.startswith(STATE_MARKER):
        raise DurableReadError("UNTRUSTED_STATE_AUTHOR_OR_MARKER")
    try:
        state = decode_state(body)
        revision = state.revision
        if state.research_id != binding.research_id:
            raise DurableReadError("STATE_WORK_MISMATCH")
        if type(revision) is not int or revision < binding.minimum_revision:
            raise DurableReadError("STATE_REVISION_ROLLBACK")
        progress = state.progress_checkpoint
        if progress is not None and (not isinstance(progress, Mapping)
                or progress.get("work_id") != binding.research_id):
            raise DurableReadError("CHECKPOINT_WORK_MISMATCH")
    except DurableReadError:
        raise
    except Exception as exc:
        raise DurableReadError("STATE_DECODE_FAILED") from exc
    return StateRead(binding, comment_id, revision, body_digest, state)


def reconcile_state(observation: StateRead, *, expected_plan_sha256: str,
                    expected_policy_sha256: str, validate_checkpoint: Callable) -> Reconciliation:
    """Check stored progress against the trusted current plan/policy fingerprints.

    Reuse Samuel's progress validator. Even a match only allows further fresh
    evidence collection; it does not establish valid unit receipts at current
    HEAD, authorize a transition, or replace Samuel state_refresh.evaluate.
    """
    if (not isinstance(observation, StateRead) or not callable(validate_checkpoint)
            or any(not isinstance(value, str) or not _SHA256.fullmatch(value)
                   for value in (expected_plan_sha256, expected_policy_sha256))):
        raise DurableReadError("TRUSTED_RECONCILIATION_INPUT_REQUIRED")
    state = observation.state
    if state.research_id != observation.binding.research_id or state.revision != observation.revision:
        raise DurableReadError("LOADED_STATE_IDENTITY_CHANGED")
    if state.progress_checkpoint is None:
        return Reconciliation("FULL_REFRESH_REQUIRED", ("CHECKPOINT_MISSING",), observation.evidence_ref)
    try:
        checkpoint = validate_checkpoint(state.progress_checkpoint)
    except Exception as exc:
        raise DurableReadError("CHECKPOINT_INVALID") from exc
    if not isinstance(checkpoint, Mapping) or checkpoint.get("work_id") != observation.binding.research_id:
        raise DurableReadError("CHECKPOINT_WORK_MISMATCH")
    reasons = tuple(reason for key, expected, reason in (
        ("plan_sha256", expected_plan_sha256, "PLAN_CHANGED"),
        ("policy_sha256", expected_policy_sha256, "POLICY_CHANGED"),
    ) if checkpoint.get(key) != expected)
    return Reconciliation("FULL_REFRESH_REQUIRED" if reasons else "FRESH_EVIDENCE_REQUIRED",
                          reasons, observation.evidence_ref)
