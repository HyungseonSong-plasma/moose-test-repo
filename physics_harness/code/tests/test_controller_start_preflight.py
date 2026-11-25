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
                trusted_sha=MAIN, read_head=lambda branch: MAIN if branch == "main" else TARGET,
                verify_authority=lambda: "central@" + MAIN)
    args.update(overrides)
    return verify_start(**args)


def test_start_observation_is_not_write_or_execution_approval():
    result = observe()
    assert result["status"] == "INIT_IDENTITIES_CHECKED"
    assert result["request"] == REQUEST
    assert not result["controller_execution_approved"]
    assert not result["write_authorized"]
    assert not result["blocker_history_checked"]
    assert not result["execution_routes_verified"]


@pytest.mark.parametrize("change", [dict(cycle_id=""), dict(controller_sha=TARGET),
                                    dict(repository="other/repo"), dict(path="a.py")])
def test_reject_invalid_start_requests(change):
    with pytest.raises(ValueError):
        observe({**REQUEST, **change})


def test_reject_target_changed_during_authority_check():
    heads = {"main": MAIN, "issue-1": TARGET}
    def authority():
        heads["issue-1"] = MAIN
        return "central@" + MAIN
    with pytest.raises(ValueError, match="TARGET_HEAD_CHANGED"):
        observe(read_head=heads.__getitem__, verify_authority=authority)
