"""Bounded contract tests and real local Git race; no external write."""
from dataclasses import dataclass, asdict, replace
import json
import subprocess
from pathlib import Path

import pytest

from physics_harness.execution.controller_pr_state import (
    PRBinding, PRStateSnapshot, PRStateHold, validate_bindings, plan_pr_state,
    classify_publication,
)


@dataclass
class State:
    research_id: str
    revision: int
    evidence: str = ""


def encode(state):
    return "<!-- samuel-controller-state -->\n" + json.dumps(asdict(state), sort_keys=True)


def decode(body):
    return State(**json.loads(body.split("\n", 1)[1]))


def fresh(old, new):
    assert old.research_id == new.research_id and new.revision > old.revision


A = PRBinding("owner/repo", 1, "issue-a", "work-a")
B = PRBinding("owner/repo", 2, "issue-b", "work-b")
H = "a" * 40


def snapshot(binding=A, head=H):
    return PRStateSnapshot(binding, head, 0, encode(State(binding.work_id, 0)), "b" * 64)


def plan(binding=A, base=None, proposed=None, **kwargs):
    return plan_pr_state(binding=binding, base=base or snapshot(binding),
                         proposed=proposed or State(binding.work_id, 1, "receipt"),
                         **({"encode_state": encode, "decode_state": decode,
                             "require_fresh_write": fresh} | kwargs))


def test_independent_pr_namespaces():
    assert validate_bindings([A, B]) == (A, B)
    assert plan(A).path != plan(B).path
    assert not plan(A).write_authorized


@pytest.mark.parametrize("binding", [replace(A, work_id="other"), replace(B, branch=A.branch),
                                     replace(A, repository="OWNER/REPO")])
def test_duplicate_ownership(binding):
    with pytest.raises(PRStateHold, match="SHARED_PR_OR_BRANCH"):
        validate_bindings([A, binding])


@pytest.mark.parametrize("branch", ["main", "issue-../bad", "issue-a.lock", "issue-a..b"])
def test_bad_branch(branch):
    with pytest.raises(PRStateHold):
        replace(A, branch=branch)


@pytest.mark.parametrize("proposed", [State("work-b", 1), State("work-a", 0),
                                     State("work-a", 2), State("work-a", True)])
def test_invalid_proposal(proposed):
    with pytest.raises(PRStateHold, match="INVALID_NEXT_REVISION"):
        plan(proposed=proposed)


def test_cross_pr_snapshot():
    with pytest.raises(PRStateHold):
        plan(A, base=snapshot(B))


def test_central_rejection():
    def reject(*args):
        raise ValueError("policy")
    with pytest.raises(PRStateHold, match="SAMUEL_VALIDATION_FAILED"):
        plan(require_fresh_write=reject)


def test_record_deterministic_and_bound():
    p = plan()
    assert p == plan()
    record = json.loads(p.record)
    assert record["expected_parent"] == H
    assert record["previous_record_sha256"] == "b" * 64
    assert record["work_id"] == A.work_id


@pytest.mark.parametrize("head,record,proof,expected", [
    (H, None, False, "READY_FOR_REVIEW"),
    ("c"*40, None, False, "HOLD_STALE_HEAD"),
    ("c"*40, b"different", True, "HOLD_RECORD_CONFLICT"),
    ("c"*40, "match", False, "HOLD_UNVERIFIED_PUBLICATION"),
    ("c"*40, "match", True, "RECORD_OBSERVED"),
    (H, "match", True, "HOLD_UNVERIFIED_PUBLICATION"),
])
def test_publication(head, record, proof, expected):
    p = plan()
    assert classify_publication(p, binding=A, current_head=head,
        record_at_path=p.record if record == "match" else record,
        verified_record_commit=proof) == expected


def git(path, *args, ok=True):
    r = subprocess.run(["git", "-C", str(path), *args], text=True, capture_output=True)
    if ok:
        assert r.returncode == 0, r.stderr
    return r


def test_real_git_parallel_prs_and_same_branch_race(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare", "--initial-branch=main")
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "--initial-branch=main")
    git(seed, "config", "user.email", "test@example.invalid")
    git(seed, "config", "user.name", "test")
    git(seed, "commit", "--allow-empty", "-m", "base")
    git(seed, "remote", "add", "origin", str(remote))
    for branch in ["main", A.branch, B.branch]:
        git(seed, "push", "origin", f"HEAD:refs/heads/{branch}")
    clients = []
    for name, binding, evidence in [("a", A, "receipt-a"), ("b", B, "receipt-b"),
                                     ("race", A, "receipt-race")]:
        client = tmp_path / name
        git(tmp_path, "clone", "-b", binding.branch, str(remote), str(client))
        git(client, "config", "user.email", "test@example.invalid")
        git(client, "config", "user.name", name)
        head = git(client, "rev-parse", "HEAD").stdout.strip()
        p = plan(binding, snapshot(binding, head), State(binding.work_id, 1, evidence))
        target = client / p.path
        target.parent.mkdir(parents=True)
        target.write_bytes(p.record)
        git(client, "add", p.path)
        git(client, "commit", "-m", "record")
        assert git(client, "rev-parse", "HEAD^").stdout.strip() == p.expected_head
        assert git(client, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").stdout.strip() == p.path
        clients.append((client, p))
    for client, p in clients[:2]:
        git(client, "push", "origin", f"HEAD:refs/heads/{p.binding.branch}")
    race, p = clients[2]
    rejected = git(race, "push", "origin", f"HEAD:refs/heads/{p.binding.branch}", ok=False)
    assert rejected.returncode != 0
    for client, p in clients[:2]:
        result = git(remote, "show", f"refs/heads/{p.binding.branch}:{p.path}")
        assert result.stdout.encode() == p.record
    # Independent branches can merge both unique paths; semantic review is separate.
    git(seed, "fetch", "origin")
    for binding in (A, B):
        git(seed, "merge", "--no-ff", "--no-edit", f"origin/{binding.branch}")
    for _, p in clients[:2]:
        assert (seed / p.path).read_bytes() == p.record
