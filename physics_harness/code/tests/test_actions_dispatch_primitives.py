"""Transport-injected tests; no network, credentials or actual dispatch."""
import pytest

from libs.command_execution.actions import ActionsDispatchError, dispatch_workflow
from libs.git_evidence.observation import observe_dispatch

REPO = "example/moose"
SHA = "a" * 40


class FakeTransport:
    repository = REPO

    def __init__(self, *, sha=SHA, response=None):
        self.sha = sha
        self.response = response
        self.posts = []

    def get(self, path, *, query=None):
        if path == "/actions/workflows/preflight.yml":
            return {"id": 10, "path": ".github/workflows/preflight.yml", "state": "active"}
        if path == "/git/ref/heads/issue-test":
            return {"ref": "refs/heads/issue-test", "object": {"type": "commit", "sha": self.sha}}
        raise AssertionError(path)

    def request(self, method, path, *, payload):
        self.posts.append((method, path, payload))
        return (204, None) if self.response is None else (200, self.response)


def dispatch(transport, **changes):
    args = dict(repository=REPO, workflow="preflight.yml", branch="issue-test",
                expected_head_sha=SHA, correlation_id="request-1")
    args.update(changes)
    return dispatch_workflow(transport, **args)


def test_dispatch_binds_current_head_and_posts_once():
    transport = FakeTransport(response={"workflow_run_id": 42})
    receipt = dispatch(transport)
    assert receipt["workflow_run_id"] == 42
    assert receipt["expected_head_sha"] == SHA
    assert transport.posts == [("POST", "/actions/workflows/10/dispatches", {
        "ref": "issue-test", "inputs": {"correlation_id": "request-1"},
        "return_run_details": True})]


@pytest.mark.parametrize("changes", [
    {"repository": "example/other"}, {"expected_head_sha": "HEAD"},
    {"branch": "../../main"}, {"workflow": "../other.yml"},
    {"inputs": {"correlation_id": "wrong"}},
])
def test_invalid_prerequisites_never_post(changes):
    transport = FakeTransport()
    with pytest.raises(ActionsDispatchError):
        dispatch(transport, **changes)
    assert transport.posts == []


def test_stale_head_never_posts():
    transport = FakeTransport(sha="b" * 40)
    with pytest.raises(ActionsDispatchError, match="DISPATCH_HEAD_MISMATCH"):
        dispatch(transport)
    assert transport.posts == []


def test_bad_response_is_not_automatically_retried():
    transport = FakeTransport(response={"workflow_run_id": True})
    with pytest.raises(ActionsDispatchError, match="RECONCILE"):
        dispatch(transport)
    assert len(transport.posts) == 1


def receipt(run_id=42, prefix=None):
    return {"repository": REPO, "workflow_id": 10, "ref": "issue-test",
            "expected_head_sha": SHA, "requested_at": "2026-01-01T00:00:00.500Z",
            "correlation_id": "request-1", "workflow_run_id": run_id,
            "correlation_run_name_prefix": prefix}


def run(run_id=42, **changes):
    result = {"id": run_id, "repository": {"full_name": REPO}, "workflow_id": 10,
              "event": "workflow_dispatch", "head_branch": "issue-test", "head_sha": SHA,
              "run_attempt": 1, "created_at": "2026-01-01T00:00:01Z",
              "status": "completed", "conclusion": "success", "display_title": "preflight:request-1"}
    result.update(changes)
    return result


def observe(r, runs, **changes):
    args = dict(repository=REPO, enumeration_complete=True, observed_at="2026-01-01T00:00:10Z")
    args.update(changes)
    return observe_dispatch(r, runs, **args)


def test_exact_direct_receipt_terminal_and_active():
    assert observe(receipt(), [run()]) == {"status": "MATCHED_TERMINAL", "matched_run_ids": [42], "conclusion": "success"}
    assert observe(receipt(), [run(status="in_progress")])["status"] == "MATCHED_ACTIVE"


@pytest.mark.parametrize("changes", [{"head_sha": "b" * 40}, {"head_branch": "main"},
                                     {"run_attempt": 2}, {"event": "push"}, {"workflow_id": 11}])
def test_direct_identity_mismatch(changes):
    assert observe(receipt(), [run(**changes)])["status"] == "BOUND_RUN_IDENTITY_MISMATCH"


def test_legacy_dispatch_requires_observable_correlation():
    assert observe(receipt(None), [run()])["status"] == "OBSERVATION_INCOMPLETE"
    r = receipt(None, "preflight:")
    assert observe(r, [run()])["status"] == "MATCHED_TERMINAL"
    assert observe(r, [run(), run(43)])["status"] == "AMBIGUOUS_MATCH"


def test_incomplete_enumeration_and_duplicate_ids_fail_closed():
    assert observe(receipt(), [], enumeration_complete=False)["status"] == "OBSERVATION_INCOMPLETE"
    assert observe(receipt(), [run(), run()])["status"] == "OBSERVATION_INCOMPLETE"


def test_visibility_window_and_wrong_repository():
    assert observe(receipt(), [])["status"] == "PENDING_VISIBILITY"
    assert observe(receipt(), [], observed_at="2026-01-01T00:02:00Z")["status"] == "NO_MATCH"
    assert observe(receipt(), [run(repository={"full_name": "example/other"})])["status"] == "OBSERVATION_INCOMPLETE"
