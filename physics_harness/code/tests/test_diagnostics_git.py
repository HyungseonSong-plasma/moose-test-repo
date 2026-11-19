"""D1/D4 P0: exact-HEAD Git inventory and scoped coverage receipts."""

import hashlib
import subprocess

import pytest

from physics_harness.code.diagnostics import (
    GitSourceProvider, ScanBudget, ScanRequest, run_scan,
)


def request(sha, **changes):
    options = dict(
        repository="example/repo", revision=sha,
        includes=(".github/workflows/*.yml",),
    )
    options.update(changes)
    return ScanRequest(**options)


SIMPLE = """\
name: Example
on:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: python -m pytest -q physics_harness/code/tests
"""


def test_exact_git_head_and_source_blob_provenance(git_factory):
    root, head = git_factory({".github/workflows/check.yml": SIMPLE})
    provider = GitSourceProvider(root)
    first = run_scan(request(head), provider)
    again = run_scan(request(head), provider)
    assert first.graph == again.graph
    assert first.receipt == again.receipt
    assert first.status == "COMPLETE"
    assert first.receipt.scanned_count == 1
    assert first.graph.scope.revision == head
    assert first.receipt.collector_versions == (("workflow", "github-actions-static-v0.1"),)
    assert {item.observation_status for item in first.graph.evidence} == {"SOURCE_DECLARED"}
    assert any(e.attributes.get("blob_sha") for e in first.graph.evidence)
    assert all(edge.evidence_ids for edge in first.graph.edges)
    assert any(item.relation == "DECLARES_RUN_COMMAND" for item in first.graph.edges)


def test_changed_worktree_is_not_relabelled_as_source_snapshot(git_factory):
    root, head = git_factory({".github/workflows/check.yml": SIMPLE})
    path = root / ".github/workflows/check.yml"
    path.write_text("name: MUTATED_WORKTREE\n", encoding="utf-8")
    result = run_scan(request(head), GitSourceProvider(root))
    assert result.status == "COMPLETE"
    assert all("MUTATED_WORKTREE" not in node.name for node in result.graph.nodes)
    assert "python -m pytest" in str(
        [node.attributes.get("declaration") for node in result.graph.nodes]
    )


def test_mismatched_head_and_missing_paths_are_not_accepted(git_factory):
    root, head = git_factory({".github/workflows/check.yml": SIMPLE})
    with pytest.raises(ValueError, match="GIT_HEAD_MISMATCH"):
        run_scan(request("0" * 40), GitSourceProvider(root))
    result = run_scan(
        request(head, includes=(".github/workflows/not-here.yml",)),
        GitSourceProvider(root),
    )
    assert result.status == "PARTIAL"
    assert "INCLUDE_PATTERN_UNMATCHED:.github/workflows/not-here.yml" in result.receipt.unresolved


def test_budget_and_excluded_paths_are_receipted(git_factory):
    root, head = git_factory({
        ".github/workflows/a.yml": SIMPLE,
        ".github/workflows/b.yml": SIMPLE,
        ".github/workflows/c.yml": SIMPLE,
    })
    partial = run_scan(
        request(head, budget=ScanBudget(max_files=1)),
        GitSourceProvider(root),
    )
    assert partial.status == "PARTIAL"
    assert [x.status for x in partial.receipt.files] == [
        "SCANNED", "SKIPPED_BUDGET", "SKIPPED_BUDGET",
    ]
    assert partial.receipt.scanned_count == 1
    excluded = run_scan(
        request(head, excludes=(".github/workflows/c.yml",)),
        GitSourceProvider(root),
    )
    assert excluded.status == "COMPLETE"
    assert excluded.receipt.files[-1].status == "EXCLUDED"
    assert ".github/workflows/c.yml" in excluded.graph.scope.excluded_paths


def test_unhandled_source_and_source_size_bounds_are_partial(git_factory):
    root, head = git_factory({
        ".github/workflows/check.yml": SIMPLE,
        "src/main.py": "print('hello')\n",
    })
    unsupported = run_scan(
        request(head, includes=("src/*.py",)), GitSourceProvider(root),
    )
    assert unsupported.status == "PARTIAL"
    assert unsupported.receipt.files[0].status == "UNSUPPORTED"
    limited = run_scan(
        request(head, budget=ScanBudget(max_bytes=3)), GitSourceProvider(root),
    )
    assert limited.status == "PARTIAL"
    assert limited.receipt.files[0].status == "SKIPPED_BUDGET"


def test_source_blob_digest_mismatch_fails_closed(git_factory):
    root, head = git_factory({".github/workflows/check.yml": SIMPLE})
    base = GitSourceProvider(root)

    class CorruptSource:
        def inventory(self, req):
            return base.inventory(req)

        def read(self, record):
            return b"corrupted"

    with pytest.raises(ValueError, match="SOURCE_BLOB_IDENTITY_MISMATCH"):
        run_scan(request(head), CorruptSource())


def test_non_regular_git_symlink_is_not_parsed(git_factory, tmp_path):
    root, head = git_factory({".github/workflows/check.yml": SIMPLE})
    link = root / ".github/workflows/redirect.yml"
    link.symlink_to("check.yml")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", "symlink"], check=True,
    )
    head = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
    ).strip()
    result = run_scan(request(head), GitSourceProvider(root))
    status_by_path = {f.path: f.status for f in result.receipt.files}
    assert status_by_path[".github/workflows/redirect.yml"] == "UNSUPPORTED"
    assert result.status == "PARTIAL"
