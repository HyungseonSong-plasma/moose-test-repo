"""Read-only fresh-runner restore from an independently enrolled PR Git history.

No fetch, mutation, scheduling or authorization. The runtime must authenticate
its checkout and independently obtain the current PR observation and enrollment
anchor (including a minimum known tip). A caller's Boolean is not proof.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from collections.abc import Callable

from .controller_git_evidence import GitEvidence
from .controller_pr_state import PRBinding, PRStateSnapshot, PRStateHold, plan_pr_state

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ROOT = "automation/controller-state/"
_MAX_COMMITS = 10_000
_MAX_RECORD = 1_000_000


@dataclass(frozen=True, slots=True)
class RestoreAnchor:
    initial: PRStateSnapshot
    minimum_revision: int
    minimum_record_sha256: str

    def __post_init__(self):
        s = self.initial
        if (not isinstance(s, PRStateSnapshot) or not isinstance(s.binding, PRBinding)
                or not isinstance(s.head, str) or not _SHA.fullmatch(s.head)
                or type(s.revision) is not int or not 0 <= s.revision < 10**16 - 1
                or not isinstance(s.record_sha256, str) or not _DIGEST.fullmatch(s.record_sha256)
                or type(self.minimum_revision) is not int
                or not s.revision <= self.minimum_revision < 10**16 - 1
                or not isinstance(self.minimum_record_sha256, str)
                or not _DIGEST.fullmatch(self.minimum_record_sha256)
                or (self.minimum_revision == s.revision
                    and self.minimum_record_sha256 != s.record_sha256)):
            raise PRStateHold("INVALID_RESTORE_ANCHOR")


@dataclass(frozen=True, slots=True)
class PRHeadObservation:
    binding: PRBinding
    head: str


@dataclass(frozen=True, slots=True)
class RestoreObservation:
    snapshot: PRStateSnapshot
    records_checked: int

    @property
    def execution_authorized(self) -> bool:
        return False


def restore_pr_state(*, reader: GitEvidence, binding: PRBinding, anchor: RestoreAnchor,
                     observe_head: Callable, verify_anchor: Callable,
                     encode_state: Callable, decode_state: Callable,
                     require_fresh_write: Callable) -> RestoreObservation:
    """Restore the last state at a fresh exact HEAD, including incomplete work.

    Verify every record as an exact replay of D3's existing planner, then compare
    the independently anchored minimum revision/digest. Re-read the PR head at
    completion. No inference of enrollment from an empty repository. Code-only
    commits are allowed; merge/nonlinear histories and foreign state writes are
    explicitly outside this bounded linear-history restore contract.
    """
    try:
        if (not isinstance(anchor, RestoreAnchor) or anchor.initial.binding != binding
                or verify_anchor(binding, anchor) is not True):
            raise PRStateHold("RESTORE_ANCHOR_UNVERIFIED")
        first = observe_head(binding)
        if (not isinstance(first, PRHeadObservation) or first.binding != binding
                or not isinstance(first.head, str) or not _SHA.fullmatch(first.head)):
            raise PRStateHold("RESTORE_HEAD_UNVERIFIED")
        initial = anchor.initial
        state = decode_state(initial.body)
        if (state.research_id != binding.work_id or type(state.revision) is not int
                or state.revision != initial.revision or encode_state(state) != initial.body):
            raise PRStateHold("RESTORE_INITIAL_STATE_MISMATCH")
        for head in (initial.head, first.head):
            if reader._git("cat-file", "-t", head).strip() != b"commit":
                raise PRStateHold("RESTORE_NOT_COMMIT")
        # Enrollment starts at a base without any records in this PR namespace.
        if reader._git("ls-tree", "-rz", "--full-tree", initial.head, "--", binding.prefix):
            raise PRStateHold("RESTORE_NONEMPTY_ENROLLMENT_BASE")
        commits = reader._git("rev-list", "--reverse", "--max-count=" + str(_MAX_COMMITS + 1),
                              initial.head + ".." + first.head).decode("ascii").splitlines()
        if len(commits) > _MAX_COMMITS:
            raise PRStateHold("RESTORE_COMMIT_LIMIT")
        parent, snapshot, checked = initial.head, initial, 0
        minimum_seen = initial.revision == anchor.minimum_revision
        for commit in commits:
            if reader._git("rev-list", "--parents", "-n", "1", commit).decode().split() != [commit, parent]:
                raise PRStateHold("RESTORE_NONLINEAR_HISTORY")
            changes = reader._changes(parent, commit)
            state_changes = [(s,p) for s,p in changes if p.startswith(_ROOT)]
            if state_changes:
                status, path = state_changes[0]
                if len(changes) != 1 or status != "A" or not path.startswith(binding.prefix):
                    raise PRStateHold("RESTORE_STATE_EDIT_OR_FOREIGN_WRITE")
                entry = reader._git("ls-tree", "-z", commit, "--", path)
                meta, sep, name = entry.rstrip(b"\0").partition(b"\t")
                mode, kind, oid = meta.decode("ascii").split()
                if (sep != b"\t" or name.decode("utf-8") != path or mode != "100644"
                        or kind != "blob" or not _SHA.fullmatch(oid)):
                    raise PRStateHold("RESTORE_RECORD_MODE")
                size = int(reader._git("cat-file", "-s", oid))
                if not 0 < size <= _MAX_RECORD:
                    raise PRStateHold("RESTORE_RECORD_LIMIT")
                raw = reader._git("cat-file", "blob", oid)
                if len(raw) != size:
                    raise PRStateHold("RESTORE_RECORD_SIZE_MISMATCH")
                proposed = decode_state(json.loads(raw)["state_body"])
                prior = PRStateSnapshot(binding, parent, snapshot.revision,
                                        snapshot.body, snapshot.record_sha256)
                plan = plan_pr_state(binding=binding, base=prior, proposed=proposed,
                    encode_state=encode_state, decode_state=decode_state,
                    require_fresh_write=require_fresh_write)
                if path != plan.path or raw != plan.record:
                    raise PRStateHold("RESTORE_RECORD_REPLAY_MISMATCH")
                snapshot = PRStateSnapshot(binding, commit, plan.revision,
                                          encode_state(proposed), sha256(raw).hexdigest())
                checked += 1
                if snapshot.revision == anchor.minimum_revision:
                    if snapshot.record_sha256 != anchor.minimum_record_sha256:
                        raise PRStateHold("RESTORE_MINIMUM_TIP_MISMATCH")
                    minimum_seen = True
            parent = commit
        if parent != first.head or not minimum_seen:
            raise PRStateHold("RESTORE_ROLLBACK_OR_UNRELATED_HEAD")
        if observe_head(binding) != first:
            raise PRStateHold("RESTORE_HEAD_CHANGED")
        return RestoreObservation(PRStateSnapshot(binding, parent, snapshot.revision,
                                    snapshot.body, snapshot.record_sha256), checked)
    except PRStateHold:
        raise
    except Exception as exc:
        raise PRStateHold("RESTORE_EVIDENCE_UNAVAILABLE") from exc
