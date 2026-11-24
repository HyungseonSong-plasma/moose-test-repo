"""P0: real bounded Git worktree before/after contract test execution."""
from __future__ import annotations

from pathlib import Path
import subprocess
from xml.etree import ElementTree as ET

import pytest

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.verification.pytest_revision_runner import run_naming_test_replay

TEST = "tests/test_contract.py"
TEST_CODE = "from api import process\n\ndef test_contract():\n    assert process(3) == 4\n"


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(("git", "-C", str(root), *args), text=True).strip()


def commit(root: Path, note: str) -> str:
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", note)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Evidence Fixture")
    (root / "tests").mkdir()
    (root / TEST).write_text(TEST_CODE)
    (root / "api.py").write_text("def process(x):\n    return x + 1\n")
    baseline = commit(root, "base")
    (root / "api.py").write_text("from new_impl import process\n")
    (root / "new_impl.py").write_text("def process(x):\n    return x + 1\n")
    candidate = commit(root, "candidate compatible extraction")
    return root, baseline, candidate


def replay(repo, *, candidate=None, test_paths=(TEST,), **kw):
    root, before, after = repo
    return run_naming_test_replay(GitSourceProvider(root), before,
                                  candidate or after, test_paths, **kw)


def test_real_same_suite_passes_on_both_exact_commits_but_is_not_permission(repo):
    result = replay(repo)
    assert result.status == "PASS_WITH_GAPS"
    assert len(result.runs) == 2
    assert all(run.exit_code == 0 and run.passed_tests == 1 for run in result.runs)
    assert result.runs[0].test_blob_sha == result.runs[1].test_blob_sha
    assert all(ET.fromstring(run.junit_xml).find(".//testcase") is not None
               for run in result.runs)
    assert all(run.junit_sha256 for run in result.runs)
    assert "REPLAY_TEST_TARGET_COVERAGE_NOT_PROVEN" in result.unresolved
    assert not result.semantic_compatibility_proven and not result.mutation_approved
    assert not result.runner_authentication_proven
    assert len(git(repo[0], "worktree", "list", "--porcelain").split("worktree ")) == 2


def test_candidate_semantic_regression_fails_same_suite(repo):
    root, before, candidate = repo
    (root / "new_impl.py").write_text("def process(x):\n    return 42\n")
    broken = commit(root, "regress")
    result = replay(repo, candidate=broken)
    assert result.status == "BLOCKED"
    assert any("REPLAY_TEST_FAILED_OR_NOT_COLLECTED:candidate" in s for s in result.blockers)
    assert result.runs[0].passed_tests == 1
    assert result.runs[1].exit_code != 0


def test_modified_contract_test_cannot_fake_compatibility(repo):
    root, _, _ = repo
    (root / TEST).write_text("def test_fake():\n    assert True\n")
    revision = commit(root, "weaken contract")
    result = replay(repo, candidate=revision)
    assert result.status == "HOLD"
    assert "REPLAY_TEST_SOURCE_CHANGED:" + TEST in result.unresolved
    assert not result.runs


def test_deleted_test_is_rejected(repo):
    root, _, _ = repo
    (root / TEST).unlink()
    git(root, "add", "-u")
    git(root, "commit", "-q", "-m", "removed tests")
    revision = git(root, "rev-parse", "HEAD")
    result = replay(repo, candidate=revision)
    assert result.status == "BLOCKED"
    assert any("REPLAY_TEST_SOURCE_MISSING" in x for x in result.blockers)


def test_worktree_content_cannot_override_exact_git_test(repo):
    root, _, _ = repo
    (root / TEST).write_text("def test_forged(): assert False\n")
    (root / "api.py").write_text("raise RuntimeError('working-tree poison')\n")
    result = replay(repo)
    assert result.status == "PASS_WITH_GAPS"


def test_test_writes_are_reported_as_side_effect(repo):
    root, _, _ = repo
    path = root / TEST
    path.write_text("from pathlib import Path\nfrom api import process\n\ndef test_contract():\n    assert process(3) == 4\n    Path('artifact.log').write_text('artifact')\n")
    before = commit(root, "contract with write")
    (root / "new_impl.py").write_text("def process(x):\n    return x + 1\n# marker\n")
    candidate = commit(root, "code change")
    out = run_naming_test_replay(GitSourceProvider(root), before, candidate, (TEST,))
    assert out.status == "PASS_WITH_GAPS"
    assert any(s.startswith("REPLAY_TEST_MUTATED_WORKTREE") for s in out.unresolved)


def test_non_ancestor_and_same_commit_rejected(repo):
    root, base, cand = repo
    result = run_naming_test_replay(GitSourceProvider(root), cand, base, (TEST,))
    assert result.status == "BLOCKED"
    assert "REPLAY_COMMITS_MISSING_OR_NOT_ANCESTOR" in result.blockers
    same = run_naming_test_replay(GitSourceProvider(root), base, base, (TEST,))
    assert same.status == "BLOCKED"
    assert "REPLAY_CANDIDATE_NOT_DISTINCT" in same.blockers


@pytest.mark.parametrize("paths", [(), ("../test_foo.py",), ("tests/foo.py",),
                                  ("tests/test_x.py", "tests/test_x.py"),
                                  tuple("tests/test_%s.py" % i for i in range(9))])
def test_bad_test_targets_rejected(repo, paths):
    with pytest.raises(ValueError):
        replay(repo, test_paths=paths)


@pytest.mark.parametrize("kwargs", [{"timeout_seconds": 0}, {"timeout_seconds": 121},
                                      {"max_output_bytes": 0}])
def test_invalid_run_budgets_rejected(repo, kwargs):
    with pytest.raises(ValueError):
        replay(repo, **kwargs)


def test_pytest_did_not_collect_any_test_is_failure(repo):
    root, _, _ = repo
    (root / TEST).write_text("# no tests\n")
    base = commit(root, "zero test baseline")
    (root / "new_impl.py").write_text("def process(x):\n    return x + 1\n# no test change\n")
    end = commit(root, "zero test candidate")
    result = run_naming_test_replay(GitSourceProvider(root), base, end, (TEST,))
    assert result.status == "BLOCKED"
    assert all(r.passed_tests == 0 for r in result.runs)


def test_timeout_is_blocked_not_unknown(repo):
    root, _, _ = repo
    (root / TEST).write_text("import time\ndef test_very_slow():\n    time.sleep(2)\n")
    base = commit(root, "slow baseline")
    (root / "new_impl.py").write_text("def process(x): return x + 1\n# changed\n")
    end = commit(root, "slow candidate")
    result = run_naming_test_replay(GitSourceProvider(root), base, end, (TEST,), timeout_seconds=1)
    assert result.status == "BLOCKED"
    assert any(r.timed_out for r in result.runs)


def test_changed_pytest_conftest_holds_even_when_test_file_unchanged(repo):
    root, _, _ = repo
    folder = root / "tests"
    (folder / "conftest.py").write_text("import pytest\n@pytest.fixture(autouse=True)\ndef noop(): pass\n")
    revision = commit(root, "test fixture added")
    result = replay(repo, candidate=revision)
    assert result.status == "HOLD" and not result.runs
    assert "REPLAY_SUITE_SUPPORT_SOURCE_CHANGED:tests/conftest.py" in result.unresolved


def test_unchanged_suite_support_config_gets_exact_git_sha(repo):
    root, _, _ = repo
    (root / "pytest.ini").write_text("[pytest]\naddopts = \n")
    baseline = commit(root, "stable config")
    (root / "new_impl.py").write_text("def process(x):\n    return x + 1\n# no behavior change\n")
    candidate = commit(root, "candidate")
    out = run_naming_test_replay(GitSourceProvider(root), baseline, candidate, (TEST,))
    assert out.status == "PASS_WITH_GAPS"
    assert len(out.pinned_suite_support_blobs) == 1
    assert out.pinned_suite_support_blobs[0][0] == "pytest.ini"


def test_changed_pytest_ini_holds(repo):
    root, _, _ = repo
    (root / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    revision = commit(root, "changed test runner config")
    out = replay(repo, candidate=revision)
    assert out.status == "HOLD"
    assert "REPLAY_SUITE_SUPPORT_SOURCE_CHANGED:pytest.ini" in out.unresolved


def test_executed_junit_artifact_consumed_by_existing_candidate_gate(repo):
    # Integration uses the canonical JUnit replay comparator in the full repo.
    pytest.importorskip("physics_harness.code.verification.junit_compare")
    from physics_harness.code.verification.junit_compare import compare_candidate_replay
    from physics_harness.code.verification.pytest_revision_runner import build_executed_replay_artifact_pair
    receipt = replay(repo)
    baseline_artifact, candidate_artifact = build_executed_replay_artifact_pair(receipt, TEST)
    comparison = compare_candidate_replay(repo[1], repo[2], baseline_artifact, candidate_artifact)
    assert comparison.status == "HOLD"
    assert not comparison.blockers
    assert "AUTHENTICATE_CI_PRODUCER_AND_ARTIFACT_ORIGIN" in comparison.unresolved
    assert not comparison.mutation_approved
