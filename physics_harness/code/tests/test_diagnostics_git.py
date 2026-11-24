"""D1/D4 P0: exact-HEAD Git inventory and scoped coverage receipts."""

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
    assert first.receipt.attempted_files == 1
    assert first.receipt.read_bytes == len(SIMPLE.encode("utf-8"))
    assert first.receipt.elapsed_seconds >= 0.0
    assert first.receipt.budget == request(head).budget
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


def test_non_regular_git_symlink_is_not_parsed(git_factory):
    root, _ = git_factory({".github/workflows/check.yml": SIMPLE})
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



@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        (("PARTIAL", "UNSUPPORTED"), "UNRESOLVED"),
        (("FAILED", "PARTIAL"), "FAILED"),
        (("COMPLETE", "UNSUPPORTED"), "UNSUPPORTED"),
        (("COMPLETE", "COMPLETE"), "SCANNED"),
    ],
)
def test_multiple_collector_coverage_is_order_independent(git_factory, outcomes, expected):
    from physics_harness.code.diagnostics import (
        CollectionResult, FactBatch, scan_scope_id,
    )

    root, sha = git_factory({".github/workflows/check.yml": SIMPLE})

    class FakeCollector:
        version = "v1"

        def __init__(self, name, status):
            self.name = name
            self.status = status

        def supports(self, record):
            return True

        def collect(self, source, request, scope_id):
            findings = (
                (f"STATIC_UNKNOWN:{self.name}",)
                if self.status == "PARTIAL" else ()
            )
            return CollectionResult(
                FactBatch(unresolved=findings), status=self.status,
            )

    registry = {
        "a": FakeCollector("a", outcomes[0]),
        "b": FakeCollector("b", outcomes[1]),
    }
    left = ScanRequest(
        repository="example/repo", revision=sha,
        includes=(".github/workflows/check.yml",),
        collectors=("a", "b"),
    )
    right = ScanRequest(
        repository="example/repo", revision=sha,
        includes=(".github/workflows/check.yml",),
        collectors=("b", "a"),
    )
    assert scan_scope_id(left) == scan_scope_id(right)
    first = run_scan(left, GitSourceProvider(root), registry=registry)
    second = run_scan(right, GitSourceProvider(root), registry=registry)
    assert first.graph == second.graph
    assert first.receipt == second.receipt
    assert first.receipt.files[0].status == expected
    assert first.receipt.files[0].collectors == ("a", "b")
    for index, status in enumerate(outcomes):
        if status != "COMPLETE":
            assert f"COLLECTOR_{status}:{'ab'[index]}" in first.receipt.files[0].details
    assert first.status == ("COMPLETE" if expected == "SCANNED" else "PARTIAL")



def test_supports_failure_is_file_failure_not_whole_scan_failure(git_factory):
    from physics_harness.code.diagnostics import CollectionResult, FactBatch

    root, sha = git_factory({".github/workflows/check.yml": SIMPLE})

    class BrokenSupport:
        name = "broken"
        version = "v1"

        def supports(self, record):
            raise RuntimeError("broken probe")

        def collect(self, source, request, scope_id):
            raise AssertionError("unreachable")

    class WorkingCollector:
        name = "working"
        version = "v1"

        def supports(self, record):
            return True

        def collect(self, source, request, scope_id):
            return CollectionResult(FactBatch(), status="COMPLETE")

    registry = {"broken": BrokenSupport(), "working": WorkingCollector()}
    req = request(sha, collectors=("working", "broken"))
    result = run_scan(req, GitSourceProvider(root), registry=registry)
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "FAILED"
    assert "COLLECTOR_SUPPORTS_FAILED:broken:RuntimeError" in (
        result.receipt.files[0].details
    )
    assert result.receipt.files[0].collectors == ("working",)
    assert result.receipt.attempted_files == 1
    assert result.receipt.scanned_count == 0
    assert any(node.kind == "file" for node in result.graph.nodes)


def test_only_supports_failure_is_reported_without_reading_source(git_factory):
    root, sha = git_factory({".github/workflows/check.yml": SIMPLE})

    class BrokenSupport:
        name = "broken"
        version = "v1"

        def supports(self, record):
            raise LookupError("unsupported external parser")

        def collect(self, source, request, scope_id):
            raise AssertionError("unreachable")

    class NoReadProvider:
        def __init__(self):
            self.backend = GitSourceProvider(root)

        def inventory(self, req):
            return self.backend.inventory(req)

        def read(self, record):
            raise AssertionError("should not read when support check fails")

    result = run_scan(
        request(sha, collectors=("broken",)), NoReadProvider(),
        registry={"broken": BrokenSupport()},
    )
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "FAILED"
    assert result.receipt.attempted_files == 0
    assert "COLLECTOR_SUPPORTS_FAILED:broken:LookupError" in (
        result.receipt.files[0].details
    )


def test_receipt_rejects_non_hex_and_noncanonical_sha():
    from physics_harness.code.diagnostics import FileCoverage

    for bad in ("z" * 40, "A" * 40, "1" * 39, "1" * 41, "a" * 39 + "g"):
        with pytest.raises(ValueError, match="FILE_RECEIPT_BLOB_REQUIRED"):
            FileCoverage("src/file.py", bad, "SCANNED")
    assert FileCoverage("src/file.py", "a" * 40, "SCANNED").blob_sha == "a" * 40


def test_naming_tree_paths_preserve_filters_and_historical_identity(git_factory, monkeypatch):
    from physics_harness.code.verification.naming_boundary import _tree_paths
    from physics_harness.code.verification.naming_consumers import _git_source_paths
    from physics_harness.code.tests.conftest import git

    root, old = git_factory({"z.py": "pass\n", "a.md": "# doc\n",
                             "a space.py": "pass\n", "line\nbreak.py": "pass\n",
                             "data.bin": b"\x00", "upper.PY": "pass\n",
                             ".py": "pass\n"})
    (root / "tool.py").write_text("pass\n")
    (root / "tool.py").chmod(0o755)
    (root / "linked.py").symlink_to("z.py")
    git(root, "add", ".")
    git(root, "update-index", "--add", "--cacheinfo", "160000," + old + ",submodule.py")
    git(root, "commit", "-qm", "nonregular and executable controls")
    current = git(root, "rev-parse", "HEAD")
    (root / "untracked.py").write_text("pass\n")
    (root / "z.py").write_text("# worktree mutation\n")
    provider = GitSourceProvider(root)
    original_git = provider._git
    calls = []

    def record(*args):
        calls.append(args)
        return original_git(*args)

    monkeypatch.setattr(provider, "_git", record)
    for revision, executable in ((old, ()), (current, ("tool.py",))):
        calls.clear()
        python = frozenset(("z.py", "a space.py", "line\nbreak.py", ".py") + executable)
        text = tuple(sorted(("z.py", "a space.py", "line\nbreak.py", "a.md") + executable))
        assert _tree_paths(provider, revision) == python
        assert calls == [("cat-file", "-t", revision),
                         ("ls-tree", "--full-tree", "-r", "-z", revision)]
        calls.clear()
        assert _git_source_paths(provider, revision) == text
        assert calls == [("cat-file", "-t", revision),
                         ("ls-tree", "--full-tree", "-r", "-z", revision)]
    assert provider.read_at_revision(old, "z.py").content == b"pass\n"
    with pytest.raises(ValueError, match="GIT_HEAD_MISMATCH"):
        provider.inventory(request(old))


@pytest.mark.parametrize("consumer,error", [
    ("boundary", "INVALID_BOUNDARY_REVISION"),
    ("consumer", "INVALID_CONSUMER_REVISION"),
])
def test_naming_tree_paths_keep_revision_errors(git_factory, consumer, error):
    from physics_harness.code.verification.naming_boundary import _tree_paths
    from physics_harness.code.verification.naming_consumers import _git_source_paths
    from physics_harness.code.tests.conftest import git

    root, head = git_factory({"a.py": "pass\n"})
    provider = GitSourceProvider(root)
    select = _tree_paths if consumer == "boundary" else _git_source_paths
    with pytest.raises(ValueError, match=error):
        select(provider, "HEAD")
    with pytest.raises(ValueError, match="GIT_SOURCE_UNAVAILABLE"):
        select(provider, "0"*40)
    blob = git(root, "rev-parse", "HEAD:a.py")
    with pytest.raises(ValueError, match=consumer.upper()+"_REVISION_NOT_COMMIT"):
        select(provider, blob)


@pytest.mark.parametrize("row,exception", [
    (b"bad-row\0", ValueError),
    (b"100644 blob " + b"0"*40 + b"\tbad\xff.py\0", UnicodeDecodeError),
])
def test_naming_tree_paths_keep_malformed_row_errors(git_factory, monkeypatch, row, exception):
    from physics_harness.code.verification.naming_boundary import _tree_paths
    from physics_harness.code.verification.naming_consumers import _git_source_paths

    root, head = git_factory({"a.py": "pass\n"})
    provider = GitSourceProvider(root)
    monkeypatch.setattr(provider, "_git", lambda *args:
                        b"commit\n" if args[0] == "cat-file" else row)
    for select in (_tree_paths, _git_source_paths):
        with pytest.raises(exception):
            select(provider, head)
