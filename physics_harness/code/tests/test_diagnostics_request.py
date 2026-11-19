"""D1 P0: bounded, explicitly scoped request and canonical IDs."""

import pytest

from physics_harness.code.diagnostics import (
    ScanBudget, ScanRequest, file_node_id, graph_edge_id, stable_id,
)


REVISION = "a" * 40


def request(**changes):
    values = dict(
        repository="example/repo", revision=REVISION,
        includes=(".github/workflows/*.yml",),
    )
    values.update(changes)
    return ScanRequest(**values)


def test_exact_revision_and_scoped_selection():
    req = request(revision="A" * 40, excludes=(".github/workflows/skip.yml",))
    assert req.revision == REVISION
    assert req.selects(".github/workflows/ci.yml")
    assert not req.selects(".github/workflows/skip.yml")
    assert not req.selects("src/main.py")


@pytest.mark.parametrize("revision", ["HEAD", "abc", "a" * 39, "z" * 40])
def test_revision_requires_exact_git_identity(revision):
    with pytest.raises(ValueError, match="exact 40-character"):
        request(revision=revision)


@pytest.mark.parametrize("pattern", ["/absolute", "a/../b", "a//b", "a\\b"])
def test_unsafe_scopes_fail_closed(pattern):
    with pytest.raises(ValueError, match="INVALID_SOURCE_PATH"):
        request(includes=(pattern,))


def test_budget_and_duplicate_safety():
    with pytest.raises(ValueError):
        ScanBudget(max_files=0)
    with pytest.raises(ValueError):
        ScanBudget(max_seconds=-1)
    with pytest.raises(ValueError):
        request(collectors=("workflow", "workflow"))
    with pytest.raises(ValueError):
        request(roots=("x", "x"))


def test_stable_logical_ids_do_not_embed_revision():
    a = file_node_id("example/repo", ".github/workflows/ci.yml")
    b = file_node_id("example/repo", ".github/workflows/ci.yml")
    assert a == b
    assert a != file_node_id("example/repo", ".github/workflows/other.yml")
    assert graph_edge_id(a, b, "REFERENCES", "edge-1") != graph_edge_id(
        a, b, "REFERENCES", "edge-2"
    )
    assert stable_id("node", "logical", "symbol") == stable_id(
        "node", "logical", "symbol"
    )
