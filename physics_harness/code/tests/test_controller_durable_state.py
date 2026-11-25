"""Read-only adapter contract: synthetic transport and decoder, no live authority."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from physics_harness.execution.controller_durable_state import (
    DurableReadError, StateBinding, STATE_MARKER, load_state, reconcile_state,
)

REPO = "owner/repo"
URL = f"https://api.github.com/repos/{REPO}/issues/10"
BINDING = StateBinding(REPO, 10, 100, 7, "issue:20", 3)
PLAN, POLICY = "a" * 64, "b" * 64


def comment(cid=11, body=STATE_MARKER + "\nstate", actor=7):
    return dict(id=cid, body=body, user={"id": actor}, updated_at="time", issue_url=URL)


def state(**kwargs):
    return SimpleNamespace(**dict(research_id="issue:20", revision=3,
        progress_checkpoint=dict(work_id="issue:20", plan_sha256=PLAN,
                                 policy_sha256=POLICY)) | kwargs)


def read(rows, *, decoder=None, count=None, page_reader=None):
    def issue(repo, number):
        assert (repo, number) == (REPO, 10)
        return dict(id=100, number=10, url=URL, comments=len(rows) if count is None else count)

    def pages(repo, number, page, size):
        assert (repo, number, size) == (REPO, 10, 100)
        return deepcopy(rows[(page - 1)*size:page*size])

    return load_state(binding=BINDING, read_issue=issue, read_comments=page_reader or pages,
                      decode_state=decoder or (lambda body: state()))


def test_full_pagination_and_stable_read():
    rows = [comment(i, "ordinary") for i in range(1, 101)] + [comment(101)]
    got = read(rows)
    assert got.comment_id == 101 and got.revision == 3
    assert "issuecomment-101@revision:3:sha256:" in got.evidence_ref


@pytest.mark.parametrize("rows,count,message", [
    ([], None, "STATE_MISSING_NOT_ENROLLMENT"),
    ([comment(), comment(12)], None, "AMBIGUOUS_STATE_COMMENT"),
    ([comment(actor=8)], None, "UNTRUSTED_STATE_AUTHOR_OR_MARKER"),
    ([comment(), comment()], None, "COMMENT_IDENTITY_INVALID"),
    ([comment()], 2, "COMMENT_ENUMERATION_INCOMPLETE"),
    ([comment(body="prefix" + STATE_MARKER)], None, "UNTRUSTED_STATE_AUTHOR_OR_MARKER"),
])
def test_ledger_rejection(rows, count, message):
    with pytest.raises(DurableReadError, match=message):
        read(rows, count=count)


def test_unstable_body_rejected():
    bodies = iter([comment(), comment(body=STATE_MARKER + "\nchanged")])
    with pytest.raises(DurableReadError, match="STATE_LEDGER_CHANGED"):
        read([comment()], page_reader=lambda *args: [next(bodies)])


@pytest.mark.parametrize("overrides,message", [
    ({"research_id": "issue:99"}, "STATE_WORK_MISMATCH"),
    ({"revision": 2}, "STATE_REVISION_ROLLBACK"),
    ({"revision": True}, "STATE_REVISION_ROLLBACK"),
    ({"progress_checkpoint": {"work_id": "issue:99"}}, "CHECKPOINT_WORK_MISMATCH"),
])
def test_decoded_identity_rejected(overrides, message):
    with pytest.raises(DurableReadError, match=message):
        read([comment()], decoder=lambda body: state(**overrides))


def test_invalid_decoder():
    def fail(body):
        raise ValueError("malformed Samuel payload")
    with pytest.raises(DurableReadError, match="STATE_DECODE_FAILED"):
        read([comment()], decoder=fail)


@pytest.mark.parametrize("plan,policy,expected", [
    (PLAN, POLICY, ()),
    ("c"*64, POLICY, ("PLAN_CHANGED",)),
    (PLAN, "c"*64, ("POLICY_CHANGED",)),
])
def test_reconciliation_requires_fresh_evidence(plan, policy, expected):
    result = reconcile_state(read([comment()]), expected_plan_sha256=plan,
                             expected_policy_sha256=policy, validate_checkpoint=deepcopy)
    assert result.reasons == expected
    assert result.status == ("FULL_REFRESH_REQUIRED" if expected else "FRESH_EVIDENCE_REQUIRED")
    assert not result.execution_authorized


def test_missing_progress_requires_full_refresh():
    result = reconcile_state(read([comment()], decoder=lambda body: state(progress_checkpoint=None)),
                             expected_plan_sha256=PLAN, expected_policy_sha256=POLICY,
                             validate_checkpoint=deepcopy)
    assert result.reasons == ("CHECKPOINT_MISSING",)
    assert result.status == "FULL_REFRESH_REQUIRED"


def test_invalid_checkpoint_fails_closed():
    def reject(value):
        raise ValueError("bad digest")
    with pytest.raises(DurableReadError, match="CHECKPOINT_INVALID"):
        reconcile_state(read([comment()]), expected_plan_sha256=PLAN,
                        expected_policy_sha256=POLICY, validate_checkpoint=reject)
