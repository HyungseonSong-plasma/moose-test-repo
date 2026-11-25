"""Controller INIT is distinct from individual mutation authorization."""
from hashlib import sha256
import json

import pytest

from physics_harness.execution.controller_preflight import verify_start


REPO = "owner/repo"
MAIN = "a" * 40
TARGET = "b" * 40
REQUEST = dict(repository=REPO, work_id="work-1", cycle_id="cycle-1",
               controller_sha=MAIN, target_branch="issue-1", target_sha=TARGET)


def observe(request=None, **overrides):
    raw = json.dumps(REQUEST if request is None else request).encode()
    args = dict(raw=raw, digest=sha256(raw).hexdigest(), repository=REPO,
                trusted_sha=MAIN, read_head=lambda branch: MAIN if branch == "main" else TARGET)
    args.update(overrides)
    return verify_start(**args)


def test_start_observation_is_not_write_or_execution_approval():
    result = observe()
    assert result["status"] == "INIT_IDENTITIES_CHECKED"
    assert result["request"] == REQUEST
    assert not result["controller_execution_approved"]
    assert not result["write_authorized"]
    assert not result["central_contracts_checked"]
    assert result["check_evidence"] == (("controller_identity", "refs/heads/main@" + MAIN),
                                         ("target_identity", "refs/heads/issue-1@" + TARGET))
    assert not result["blocker_history_checked"]
    assert not result["execution_routes_verified"]


@pytest.mark.parametrize("change", [dict(cycle_id=""), dict(controller_sha=TARGET),
                                    dict(repository="other/repo"), dict(path="a.py")])
def test_reject_invalid_start_requests(change):
    with pytest.raises(ValueError):
        observe({**REQUEST, **change})


def test_reject_target_changed_during_check():
    revisions = iter((TARGET, MAIN))

    def read_head(branch):
        return MAIN if branch == "main" else next(revisions)

    with pytest.raises(ValueError, match="TARGET_HEAD_CHANGED"):
        observe(read_head=read_head)


def test_reject_controller_changed_during_check():
    revisions = iter((MAIN, TARGET))

    def read_head(branch):
        return next(revisions) if branch == "main" else TARGET

    from libs.command_execution.preflight import PreflightError
    with pytest.raises(PreflightError, match="STALE_REVISION_AFTER_CHECK:controller_identity"):
        observe(read_head=read_head)


def test_reject_incorrect_request_hash():
    with pytest.raises(ValueError, match="REQUEST_DIGEST_MISMATCH"):
        observe(digest="0" * 64)
