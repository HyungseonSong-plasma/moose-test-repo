"""Controller INIT composition tests; injected observations, no live providers."""
from hashlib import sha256
import json

import pytest

from libs.command_execution.preflight import PreflightError
from physics_harness.execution.controller_orchestrator import INIT_CHECKS, collect_cycle_init


MAIN = "a" * 40
TARGET = "b" * 40
REPO = "owner/repo"
REQUEST = dict(repository=REPO, work_id="work-1", cycle_id="cycle-1",
               controller_sha=MAIN, target_branch="issue-1", target_sha=TARGET)


def observe(verifiers, *, request=None, heads=None, digest=None):
    raw = json.dumps(REQUEST if request is None else request).encode()
    if heads is None:
        heads = {"main": MAIN, "issue-1": TARGET}
    return collect_cycle_init(raw=raw, digest=digest or sha256(raw).hexdigest(),
                              repository=REPO, trusted_sha=MAIN,
                              read_head=heads.__getitem__, verifiers=verifiers)


def ports():
    return {name: lambda request, name=name: name + ":" + request["cycle_id"]
            for name in INIT_CHECKS}


def test_fixed_order_and_non_authorizing_receipt():
    called = []

    def verify(request, name):
        assert dict(request) == REQUEST
        called.append(name)
        return "receipt:" + name

    result = observe({name: lambda request, name=name: verify(request, name)
                      for name in reversed(INIT_CHECKS)})
    assert tuple(called) == INIT_CHECKS
    assert result.phase == "INIT"
    assert result.status == "INIT_EVIDENCE_COLLECTED"
    assert not result.controller_execution_approved
    assert not result.write_authorized
    assert result.observations.check_evidence == tuple(
        (name, "receipt:" + name) for name in INIT_CHECKS)
    with pytest.raises(TypeError):
        result.request["cycle_id"] = "changed"


@pytest.mark.parametrize("name", INIT_CHECKS)
def test_missing_verifier_stops(name):
    checks = ports()
    del checks[name]
    with pytest.raises(ValueError, match="INIT_VERIFIER_SET_MISMATCH"):
        observe(checks)


def test_checkpoint_or_blocker_failure_stops_later_checks():
    checks = ports()

    def blocked(request):
        raise ValueError("UNRESOLVED_BLOCKER")

    def unexpected(request):
        pytest.fail("later verifier must not run")

    checks["blocker_history"] = blocked
    checks["execution_routes"] = unexpected
    with pytest.raises(ValueError, match="UNRESOLVED_BLOCKER"):
        observe(checks)


def test_empty_reference_rejected():
    checks = ports()
    checks["checkpoint_history"] = lambda request: ""
    with pytest.raises(PreflightError, match="CHECK_EVIDENCE_MISSING:checkpoint_history"):
        observe(checks)


@pytest.mark.parametrize("branch", ["main", "issue-1"])
def test_revision_changes_during_verifier_stop(branch):
    checks = ports()
    heads = {"main": MAIN, "issue-1": TARGET}

    def change(request):
        heads[branch] = "c" * 40
        return "receipt"

    checks["work_enrollment"] = change
    checks["checkpoint_history"] = lambda request: pytest.fail("stale cycle advanced")
    with pytest.raises((ValueError, PreflightError), match="TARGET_HEAD_CHANGED|STALE_REVISION_AFTER_CHECK"):
        observe(checks, heads=heads)


def test_each_cycle_uses_fresh_bound_request():
    checks = ports()
    first = observe(checks)
    second = observe(checks, request={**REQUEST, "cycle_id": "cycle-2"})
    assert first.observations.request_sha256 != second.observations.request_sha256
    assert dict(second.observations.check_evidence)["checkpoint_history"] == "checkpoint_history:cycle-2"


def test_digest_mismatch_prevents_any_port_call():
    checks = {name: lambda request: pytest.fail("bad request reached verifier")
              for name in INIT_CHECKS}
    with pytest.raises(ValueError, match="REQUEST_DIGEST_MISMATCH"):
        observe(checks, digest="0" * 64)
