"""Shared JUnit and pytest observations without naming policy."""
from hashlib import sha256

import pytest

from libs.test_verification import compare_case_outcomes, parse_junit, run_pytest
from physics_harness.code.verification.junit_compare import (
    ReplayArtifact, compare_replay_artifacts,
)


def parse(xml, *, max_bytes=8_000_000):
    return parse_junit(xml, sha256(xml).hexdigest(), max_bytes=max_bytes)


def test_junit_outcomes_and_naming_adapter_preserve_policy():
    before = b'<testsuite><testcase classname="x" name="a"/><testcase classname="x" name="b"/></testsuite>'
    after = b'<testsuite><testcase classname="x" name="a"><failure/></testcase><testcase classname="x" name="c"><skipped/></testcase></testsuite>'
    a, blocked, gaps = parse(before)
    b, blocked2, gaps2 = parse(after)
    assert not (blocked or gaps or blocked2 or gaps2)
    findings, unresolved = compare_case_outcomes(a, b)
    assert findings == {"BASELINE_TEST_MISSING:x::b", "CANDIDATE_TEST_FAILED:x::a"}
    assert unresolved == {"NEW_CANDIDATE_TEST:x::c", "CANDIDATE_TEST_SKIPPED:x::c"}
    left = ReplayArtifact("a" * 40, before, sha256(before).hexdigest(), "baseline")
    right = ReplayArtifact("b" * 40, after, sha256(after).hexdigest(), "candidate")
    receipt = compare_replay_artifacts(left, right)
    assert set(receipt.blockers) == findings
    assert unresolved <= set(receipt.unresolved)
    assert receipt.status == "BLOCKED"
    assert not receipt.mutation_approved


@pytest.mark.parametrize("xml,reason", [
    (b'<testsuite><testcase name="a"/><testcase name="a"/></testsuite>',
     "MISSING_OR_DUPLICATE_TEST_ID"),
    (b'<!DOCTYPE testsuite><testsuite/>', "UNTRUSTED_XML_DECLARATION"),
    (b'<broken', "INVALID_JUNIT_XML"),
    (b'<other/>', "UNEXPECTED_JUNIT_ROOT"),
])
def test_junit_validation_preserves_blockers(xml, reason):
    _, blocked, _ = parse(xml)
    assert reason in blocked


def test_junit_size_and_digest():
    xml = b'<testsuite/>'
    assert parse(xml, max_bytes=1) == ({}, set(), {"JUNIT_SIZE_LIMIT"})
    assert parse_junit(xml, "0" * 64, max_bytes=100)[1] == {"JUNIT_DIGEST_MISMATCH"}


def test_real_pytest_observations_and_existing_receipt_guard(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test_example.py").write_text(
        "def test_example():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    receipt = tmp_path / "junit.xml"
    run = run_pytest("test_example.py", workspace, tmp_path, 30, 100_000, receipt)
    assert run.exit_code == 0 and run.passed_tests == 1
    assert not run.timed_out and not run.output_truncated
    assert run.junit_xml == receipt.read_bytes()
    assert sha256(run.junit_xml).hexdigest() == run.junit_sha256
    cases, blockers, unresolved = parse(run.junit_xml)
    assert list(cases.values()) == ["PASSED"]
    assert not blockers and not unresolved
    with pytest.raises(ValueError, match="PYTEST_JUNIT_DESTINATION_ALREADY_EXISTS"):
        run_pytest("test_example.py", workspace, tmp_path, 30, 100_000, receipt)
    with pytest.raises(ValueError, match="INVALID_PYTEST_TARGET"):
        run_pytest("-bad/test_example.py", workspace, tmp_path, 30, 100_000,
                   tmp_path / "other.xml")
