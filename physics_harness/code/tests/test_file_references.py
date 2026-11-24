"""File-reference resolution uses exact Git inventory and explicit bases."""

from dataclasses import replace

import pytest

from physics_harness.code.analysis import resolve_file_references
from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest, run_scan


def scan(git_factory, files, includes=("*.json",)):
    root, sha = git_factory(files)
    provider = GitSourceProvider(root)
    result = run_scan(ScanRequest("example/repo", sha, includes, collectors=("json",)), provider)
    return provider, result


def resolve(provider, result, bases=("REPOSITORY_ROOT", "OWNER_DIRECTORY")):
    bindings = {e.id: bases for e in result.graph.edges}
    return resolve_file_references(result.graph, result.receipt, provider, bases_by_edge=bindings)


def test_same_literal_different_owner_and_explicit_base(git_factory):
    provider, result = scan(git_factory, {
        "a/ref.json": '{"path":"case.i"}', "b/ref.json": '{"path":"case.i"}',
        "a/case.i": "a", "b/case.i": "b", "case.i": "root",
    })
    report = resolve(provider, result, ("OWNER_DIRECTORY",))
    rows = {r.source_path: r for r in report.rows}
    assert rows["a/ref.json"].targets[0].path == "a/case.i"
    assert rows["b/ref.json"].targets[0].path == "b/case.i"
    assert rows["a/ref.json"].targets[0].blob_sha != rows["b/ref.json"].targets[0].blob_sha
    assert all(r.status == "RESOLVED_CANDIDATE" for r in rows.values())
    assert all(r.targets[0].coverage == "OUT_OF_SCOPE" for r in rows.values())
    assert not report.safe_to_delete and not report.global_consumer_closed
    ambiguous = resolve(provider, result)
    assert all(r.status == "AMBIGUOUS" and len(r.targets) == 2 for r in ambiguous.rows)


def test_no_basename_fallback_missing_and_undeclared_base(git_factory):
    provider, result = scan(git_factory, {
        "doc/ref.json": '{"path":"wrong/case.i"}', "other/case.i": "",
    })
    row, = resolve(provider, result).rows
    assert row.status == "MISSING"
    assert row.attempted_paths == ("doc/wrong/case.i", "wrong/case.i")
    assert not row.targets
    row, = resolve_file_references(result.graph, result.receipt, provider,
                                   bases_by_edge={}).rows
    assert row.status == "UNRESOLVED"
    assert row.reason == "PATH_BASE_UNDECLARED"


def test_owner_relative_parent_escape_and_dynamic(git_factory):
    provider, result = scan(git_factory, {
        "doc/ref.json": '["../case.i","../../case.i","inputs/*.i"]',
        "case.i": "",
    })
    rows = {r.literal: r for r in resolve(provider, result, ("OWNER_DIRECTORY",)).rows}
    assert rows["../case.i"].status == "RESOLVED_CANDIDATE"
    assert rows["../../case.i"].status == "UNRESOLVED"
    assert rows["inputs/*.i"].reason == "DYNAMIC_OR_UNSUPPORTED_EXPRESSION"


def test_target_coverage_is_not_promoted(git_factory):
    provider, result = scan(git_factory, {
        "ref.json": '{"ref":"target.json"}', "target.json": '{}',
    })
    row, = resolve(provider, result).rows
    assert row.status == "RESOLVED_CANDIDATE"
    assert row.targets[0].coverage == "SCANNED"
    assert row.attempted_paths == ("target.json",)
    assert row.evidence_ids


def test_cross_head_and_forged_receipt_rejected(git_factory):
    provider, result = scan(git_factory, {"ref.json": '"case.i"', "case.i": ""})
    other, _ = scan(git_factory, {"ref.json": '"other.i"'})
    with pytest.raises(ValueError, match="GIT_HEAD_MISMATCH"):
        resolve(other, result)
    bad = replace(result.receipt, revision="a" * 40)
    with pytest.raises(ValueError, match="INVALID_SOURCE_RECEIPT"):
        resolve_file_references(result.graph, bad, provider, bases_by_edge={})


def test_invalid_base_binding_rejected(git_factory):
    provider, result = scan(git_factory, {"ref.json": '"case.i"'})
    edge, = result.graph.edges
    with pytest.raises(ValueError, match="INVALID_FILE_REFERENCE_BASES"):
        resolve_file_references(result.graph, result.receipt, provider,
                                bases_by_edge={edge.id: ("CWD_GUESS",)})
    with pytest.raises(ValueError, match="UNKNOWN_FILE_REFERENCE_EDGE"):
        resolve_file_references(result.graph, result.receipt, provider,
                                bases_by_edge={"bogus": ("REPOSITORY_ROOT",)})


def test_nonregular_git_target_not_resolved(git_factory):
    from .conftest import git

    root, _ = git_factory({"ref.json": '"alias.i"', "real.i": "payload"})
    (root / "alias.i").symlink_to("real.i")
    git(root, "add", "alias.i")
    git(root, "commit", "-q", "-m", "symlink negative control")
    provider = GitSourceProvider(root)
    result = run_scan(ScanRequest("example/repo", git(root, "rev-parse", "HEAD"),
                                  ("*.json",), collectors=("json",)), provider)
    row, = resolve(provider, result, ("REPOSITORY_ROOT",)).rows
    assert row.status == "NON_REGULAR"
    assert row.targets[0].mode == "120000"
    assert row.targets[0].path == "alias.i"


def test_root_path_resolution_is_bound_to_git_blob_not_worktree(git_factory):
    from .conftest import git

    provider, result = scan(git_factory, {
        "docs/contract.json": '{"reference":"physics_app/ci/case.i"}',
        "physics_app/ci/case.i": "original",
    })
    expected = git(provider.root, "rev-parse", "HEAD:physics_app/ci/case.i")
    (provider.root / "physics_app/ci/case.i").write_text("uncommitted mutation")
    row, = resolve(provider, result, ("REPOSITORY_ROOT",)).rows
    assert row.status == "RESOLVED_CANDIDATE"
    assert row.targets[0].blob_sha == expected
    assert row.source_path == "docs/contract.json"
