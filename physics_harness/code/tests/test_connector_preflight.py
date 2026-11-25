"""Unit tests for preflight sequencing; no live GitHub or mutation."""
from hashlib import sha256

import pytest

from libs.command_execution.preflight import PreflightCheck, PreflightError, run_preflight
from physics_harness.execution.connector_policy_probe import _strict_json


HEAD = "a" * 40
RAW = b"request"


def observe(**overrides):
    args = dict(
        request_bytes=RAW,
        expected_request_sha256=sha256(RAW).hexdigest(),
        expected_revision=HEAD,
        read_revision=lambda: HEAD,
        required_checks=("policy", "target"),
        checks=(PreflightCheck("policy", lambda: "policy-blob"),
                PreflightCheck("target", lambda: "target-blob")),
    )
    args.update(overrides)
    return run_preflight(**args)


def test_ordered_request_and_revision_receipt_is_not_authorization():
    receipt = observe()
    assert receipt.request_sha256 == sha256(RAW).hexdigest()
    assert receipt.revision == HEAD
    assert receipt.check_evidence == (("policy", "policy-blob"), ("target", "target-blob"))
    assert receipt.write_authorized is False


@pytest.mark.parametrize("kwargs, reason", [
    ({"expected_request_sha256": "0" * 64}, "REQUEST_DIGEST_MISMATCH"),
    ({"expected_revision": "main"}, "EXACT_REVISION_READER_REQUIRED"),
    ({"read_revision": lambda: "b" * 40}, "STALE_REVISION_BEFORE_CHECKS"),
    ({"required_checks": ("target", "policy")}, "REQUIRED_CHECK_SET_MISMATCH"),
    ({"required_checks": ("policy", "policy")}, "REQUIRED_CHECK_SET_MISMATCH"),
    ({"checks": (PreflightCheck("policy", lambda: ""), PreflightCheck("target", lambda: "ok"))},
     "CHECK_EVIDENCE_MISSING:policy"),
])
def test_incomplete_or_mismatched_preflight_rejected(kwargs, reason):
    with pytest.raises(PreflightError, match=reason):
        observe(**kwargs)


def test_head_change_after_policy_stops_later_check():
    revisions = iter((HEAD, "b" * 40))
    called = []
    with pytest.raises(PreflightError, match="STALE_REVISION_AFTER_CHECK:policy"):
        observe(read_revision=lambda: next(revisions), checks=(
            PreflightCheck("policy", lambda: "ok"),
            PreflightCheck("target", lambda: called.append(True)),
        ))
    assert called == []


def test_policy_error_propagates_without_later_check():
    called = []

    def denied():
        raise ValueError("DENIED")

    with pytest.raises(ValueError, match="DENIED"):
        observe(checks=(PreflightCheck("policy", denied),
                        PreflightCheck("target", lambda: called.append(True))))
    assert called == []


def test_adapter_rejects_duplicate_request_keys():
    with pytest.raises(ValueError, match="DUPLICATE_JSON_KEY"):
        _strict_json(b'{"branch":"issue-a","branch":"main"}')
