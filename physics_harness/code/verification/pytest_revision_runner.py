"""Explicit, bounded two-revision test replay on immutable Git snapshots.

Only a trusted caller should invoke this executor: repository tests execute
arbitrary code. Git worktrees separate *tracked files* from the user's checkout,
but are NOT an OS/security/network sandbox. Neither passing tests nor this
runner's self-reported receipt is permission to rename or merge code.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

from libs.test_verification.pytest_runner import run_pytest

from ..diagnostics.providers.git import GitSourceProvider
from ..diagnostics.request import normalized_path

_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True, slots=True)
class NamingReplayRun:
    revision: str
    test_path: str
    test_blob_sha: str
    command: tuple[str, ...]
    exit_code: int | None
    passed_tests: int
    stdout_sha256: str
    stderr_sha256: str
    timed_out: bool
    worktree_changed: bool
    output_truncated: bool
    junit_xml: bytes = b""
    junit_sha256: str = ""


@dataclass(frozen=True, slots=True)
class NamingReplayReceipt:
    baseline_revision: str
    candidate_revision: str
    test_paths: tuple[str, ...]
    pinned_suite_support_blobs: tuple[tuple[str, str], ...]
    runner_python: str
    runner_version: str
    status: str  # PASS_WITH_GAPS / HOLD / BLOCKED
    runs: tuple[NamingReplayRun, ...]
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]
    required_checks: tuple[str, ...]

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False

    @property
    def mutation_approved(self) -> bool:
        return False

    @property
    def runner_authentication_proven(self) -> bool:
        return False


def _run_git(provider: GitSourceProvider, *args: str) -> bytes:
    return provider._git(*args)


def _validate_tests(paths: tuple[str, ...]) -> None:
    if not isinstance(paths, tuple) or not paths or len(paths) > 8:
        raise ValueError("INVALID_REPLAY_TEST_PATHS")
    if len(set(paths)) != len(paths):
        raise ValueError("DUPLICATE_REPLAY_TEST_PATHS")
    for path in paths:
        if not isinstance(path, str):
            raise ValueError("INVALID_REPLAY_TEST_PATH")
        normalized_path(path)
        if not (path.endswith(".py") and Path(path).name.startswith("test_")):
            raise ValueError("REPLAY_REQUIRES_PYTEST_MODULE")


def _support_sources(test_paths: tuple[str, ...]) -> tuple[str, ...]:
    # Pytest config and ancestor conftest files affect test collection,
    # injected fixtures and how assertions execute even when tests are unchanged.
    paths = {"pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "conftest.py"}
    for path in test_paths:
        parts = PurePosixPath(path).parts[:-1]
        for n in range(1, len(parts) + 1):
            paths.add("/".join(parts[:n]) + "/conftest.py")
    return tuple(sorted(paths))


def _worktree(provider: GitSourceProvider, destination: Path, revision: str):
    args = ("worktree", "add", "--detach", "--", str(destination), revision)
    try:
        _run_git(provider, *args)
    except ValueError as exc:
        raise ValueError("REPLAY_WORKTREE_CREATE_FAILED") from exc


def _remove_worktree(provider: GitSourceProvider, destination: Path) -> None:
    # Cleanup must happen even after a timeout, failure or test-sourced edits.
    _run_git(provider, "worktree", "remove", "--force", str(destination))


def _execute(provider: GitSourceProvider, revision: str, path: str, sha: str,
             workspace: Path, home: Path, timeout_seconds: int,
             max_output_bytes: int, junit_destination: Path) -> NamingReplayRun:
    observed = run_pytest(path, workspace, home, timeout_seconds,
                          max_output_bytes, junit_destination)
    dirty = bool(subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True, check=False, timeout=10).stdout)
    return NamingReplayRun(
        revision, path, sha, observed.command, observed.exit_code,
        observed.passed_tests, observed.stdout_sha256, observed.stderr_sha256,
        observed.timed_out, dirty, observed.output_truncated,
        observed.junit_xml, observed.junit_sha256)


def run_naming_test_replay(
    provider: GitSourceProvider, baseline_revision: str, candidate_revision: str,
    test_paths: tuple[str, ...], *, timeout_seconds: int = 30,
    max_output_bytes: int = 1_000_000,
) -> NamingReplayReceipt:
    """Execute identical *tracked* contract tests at two exact commit SHAs.

    This is **explicit execution**, not a pure source audit. Only invoke for
    vetted, user-authorized test code in a trusted CI runner. No shell calls,
    arbitrary command strings, baseline source mutation, network sandboxing or
    implicit external auth. The caller must separately prove test relevance.
    """
    if not isinstance(provider, GitSourceProvider):
        raise TypeError("REPLAY_GIT_PROVIDER_REQUIRED")
    for rev in (baseline_revision, candidate_revision):
        if not isinstance(rev, str) or not _SHA.fullmatch(rev):
            raise ValueError("INVALID_REPLAY_REVISION")
    _validate_tests(test_paths)
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 120:
        raise ValueError("INVALID_REPLAY_TIMEOUT")
    if type(max_output_bytes) is not int or not 1024 <= max_output_bytes <= 5_000_000:
        raise ValueError("INVALID_REPLAY_OUTPUT_LIMIT")
    blockers: set[str] = set()
    unknown: set[str] = {
        "REPLAY_IS_NOT_A_PROCESS_OR_NETWORK_SANDBOX",
        "REPLAY_TEST_TARGET_COVERAGE_NOT_PROVEN",
        "REPLAY_TEST_DEPENDENCY_CLOSURE_NOT_PROVEN",
        "REPLAY_EXTERNAL_AND_DYNAMIC_CONSUMERS_UNVERIFIED",
        "REPLAY_RUNNER_IDENTITY_NOT_AUTHENTICATED",
    }
    checks = ("AUTHENTICATE_CI_EXECUTION_AND_TOOLCHAIN",
              "CONFIRM_TESTS_EXERCISE_AFFECTED_CONTRACTS",
              "VERIFY_EXTERNAL_CONSUMER_AND_PUBLIC_CONTRACT_COMPATIBILITY",
              "VERIFY_POST_INTEGRATION_HEAD_AND_ROLLBACK")
    runs = []
    if baseline_revision == candidate_revision:
        blockers.add("REPLAY_CANDIDATE_NOT_DISTINCT")
    try:
        _run_git(provider, "cat-file", "-e", baseline_revision + "^{commit}")
        _run_git(provider, "cat-file", "-e", candidate_revision + "^{commit}")
        _run_git(provider, "merge-base", "--is-ancestor", baseline_revision, candidate_revision)
    except ValueError:
        blockers.add("REPLAY_COMMITS_MISSING_OR_NOT_ANCESTOR")
    verified: dict[tuple[str, str], str] = {}
    support_blobs: dict[str, str] = {}
    if not blockers:
        for path in test_paths:
            try:
                base = provider.read_at_revision(baseline_revision, path)
                cand = provider.read_at_revision(candidate_revision, path)
                verified[(baseline_revision, path)] = base.record.blob_sha
                verified[(candidate_revision, path)] = cand.record.blob_sha
                if base.record.blob_sha != cand.record.blob_sha:
                    unknown.add("REPLAY_TEST_SOURCE_CHANGED:" + path)
            except ValueError:
                blockers.add("REPLAY_TEST_SOURCE_MISSING_OR_UNTRUSTED:" + path)
    if not blockers:
        try:
            before_paths = set(_run_git(provider, "ls-tree", "-r", "--name-only", "-z",
                                        baseline_revision).decode("utf-8", "strict").strip("\0").split("\0"))
            after_paths = set(_run_git(provider, "ls-tree", "-r", "--name-only", "-z",
                                       candidate_revision).decode("utf-8", "strict").strip("\0").split("\0"))
            for path in _support_sources(test_paths):
                if path not in before_paths and path not in after_paths:
                    continue
                if path not in before_paths or path not in after_paths:
                    unknown.add("REPLAY_SUITE_SUPPORT_SOURCE_CHANGED:" + path)
                    continue
                first = provider.read_at_revision(baseline_revision, path)
                second = provider.read_at_revision(candidate_revision, path)
                if first.record.blob_sha != second.record.blob_sha:
                    unknown.add("REPLAY_SUITE_SUPPORT_SOURCE_CHANGED:" + path)
                else:
                    support_blobs[path] = first.record.blob_sha
        except (ValueError, UnicodeError):
            blockers.add("REPLAY_SUITE_SUPPORT_SOURCE_UNREADABLE")
    # Test-source parity is mandatory for this small baseline-compatible replay.
    if not blockers and not any(
            x.startswith(("REPLAY_TEST_SOURCE_CHANGED", "REPLAY_SUITE_SUPPORT_SOURCE_CHANGED"))
            for x in unknown):
        with tempfile.TemporaryDirectory(prefix="naming-git-replay-") as td:
            root = Path(td)
            for label, rev in (("baseline", baseline_revision), ("candidate", candidate_revision)):
                location = root / label
                added = False
                try:
                    _worktree(provider, location, rev)
                    added = True
                    for index, path in enumerate(test_paths):
                        junit_destination = root / (label + "-" + str(index) + ".xml")
                        run = _execute(provider, rev, path, verified[(rev, path)],
                                       location, root, timeout_seconds, max_output_bytes,
                                       junit_destination)
                        runs.append(run)
                        if run.exit_code != 0 or run.passed_tests < 1 or run.timed_out:
                            blockers.add("REPLAY_TEST_FAILED_OR_NOT_COLLECTED:" + label + ":" + path)
                        if not run.junit_xml or len(run.junit_xml) > 8_000_000:
                            blockers.add("REPLAY_JUNIT_MISSING_OR_TOO_LARGE:" + label + ":" + path)
                        if run.output_truncated:
                            unknown.add("REPLAY_TEST_OUTPUT_LIMIT:" + label + ":" + path)
                        if run.worktree_changed:
                            unknown.add("REPLAY_TEST_MUTATED_WORKTREE:" + label + ":" + path)
                except (ValueError, OSError, subprocess.TimeoutExpired):
                    blockers.add("REPLAY_WORKTREE_OR_EXECUTION_FAILED:" + label)
                finally:
                    if added:
                        try:
                            _remove_worktree(provider, location)
                        except ValueError:
                            blockers.add("REPLAY_WORKTREE_CLEANUP_FAILED:" + label)
    if not blockers and len(runs) == 2 * len(test_paths):
        for path in test_paths:
            before = next(x for x in runs if x.revision == baseline_revision and x.test_path == path)
            after = next(x for x in runs if x.revision == candidate_revision and x.test_path == path)
            if before.passed_tests != after.passed_tests:
                blockers.add("REPLAY_TEST_CASE_COUNT_CHANGED:" + path)
    status = "BLOCKED" if blockers else (
        "HOLD" if not runs else "PASS_WITH_GAPS")
    return NamingReplayReceipt(baseline_revision, candidate_revision, test_paths,
        tuple(sorted(support_blobs.items())), sys.executable, sys.version.split(" ")[0], status, tuple(runs),
        tuple(sorted(blockers)), tuple(sorted(unknown)), checks)


def build_executed_replay_artifact_pair(
    receipt: NamingReplayReceipt, test_path: str,
):
    """Convert *real run-produced* JUnit files into canonical read-only replay inputs.

    The receiving compare_candidate_replay recomputes hashes/test IDs. This
    handoff does NOT establish the identity/authorization of the CI producer.
    """
    from .junit_compare import ReplayArtifact  # canonical v0.6 JUnit validator
    if not isinstance(receipt, NamingReplayReceipt) or test_path not in receipt.test_paths:
        raise ValueError("INVALID_EXECUTED_REPLAY_INPUT")
    observed = {(r.revision, r.test_path): r for r in receipt.runs}
    refs = []
    for revision in (receipt.baseline_revision, receipt.candidate_revision):
        run = observed.get((revision, test_path))
        if run is None or not run.junit_xml or not run.junit_sha256:
            raise ValueError("EXECUTED_REPLAY_JUNIT_NOT_AVAILABLE")
        refs.append(ReplayArtifact(revision, run.junit_xml, run.junit_sha256,
                      "unattested-worktree-pytest:" + revision))
    return tuple(refs)


__all__ = ["NamingReplayRun", "NamingReplayReceipt", "run_naming_test_replay",
           "build_executed_replay_artifact_pair"]
