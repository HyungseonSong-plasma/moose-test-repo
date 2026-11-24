"""D5 P0: source-pinned GitHub Actions static facts, never runtime PASS."""

import pytest

from physics_harness.code.diagnostics import (
    GitSourceProvider, ScanRequest, run_scan,
)


WORKFLOW = """\
name: Example
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - id: check
        run: python -m pytest -q physics_harness/code/tests
  build:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo done
"""


def scan(git_factory, content, **options):
    root, sha = git_factory({".github/workflows/check.yml": content})
    req = ScanRequest(
        repository="example/repo",
        revision=sha,
        includes=(".github/workflows/check.yml",),
        **options,
    )
    return run_scan(req, GitSourceProvider(root))


def test_workflow_job_step_dependency_trigger_and_run_are_declared_only(git_factory):
    result = scan(git_factory, WORKFLOW)
    assert result.status == "COMPLETE"
    edges = {e.relation for e in result.graph.edges}
    assert {
        "DECLARES_WORKFLOW", "DECLARES_TRIGGER", "DECLARES_JOB",
        "NEEDS_JOB", "DECLARES_STEP", "DECLARES_RUN_COMMAND",
        "DECLARES_ACTION_USE",
    }.issubset(edges)
    assert len([n for n in result.graph.nodes if n.kind == "workflow_job"]) == 2
    assert len([n for n in result.graph.nodes if n.kind == "workflow_event"]) == 2
    assert "on" not in [n.name for n in result.graph.nodes if n.kind == "workflow_event"]
    trigger_edges = [e for e in result.graph.edges if e.relation == "DECLARES_TRIGGER"]
    assert all(e.attributes["filter_declaration"]["branches"] == ("main",)
               for e in trigger_edges)
    assert all(e.evidence_ids for e in result.graph.edges)
    assert all(ev.observation_status == "SOURCE_DECLARED" for ev in result.graph.evidence)
    assert not result.graph.claims
    assert not any(x in edges for x in ("EXECUTED", "RUNTIME_PASS", "UNNECESSARY_CI"))
    assert any(n.attributes.get("declaration", "").startswith("python -m pytest")
               for n in result.graph.nodes)


def test_missing_needs_job_kept_as_placeholder(git_factory):
    source = WORKFLOW.replace("needs: lint", "needs: non_existent")
    result = scan(git_factory, source)
    assert result.status == "PARTIAL"
    assert any(node.kind == "unresolved" for node in result.graph.nodes)
    assert any(edge.relation == "NEEDS_JOB_CANDIDATE" for edge in result.graph.edges)
    assert any(item.observation_status == "UNRESOLVED" for item in result.graph.evidence)
    assert result.receipt.files[0].status == "UNRESOLVED"


def test_dynamic_conditions_matrix_and_expressions_are_not_observed(git_factory):
    source = """\
on: [push]
jobs:
  t:
    if: ${{ github.ref == 'refs/heads/main' }}
    strategy:
      matrix:
        python: ['3.10', '3.11']
    steps:
      - run: echo ${{ matrix.python }}
"""
    result = scan(git_factory, source)
    assert result.status == "PARTIAL"
    assert any("DYNAMIC_JOB_CONDITION" in value for value in result.receipt.files[0].details)
    assert any("MATRIX_EXPANSION_NOT_OBSERVED" in value for value in result.receipt.files[0].details)
    assert all(e.observation_status != "RUNTIME_OBSERVED" for e in result.graph.evidence)


def test_invalid_yaml_and_duplicate_keys_fail_partial_not_false_complete(git_factory):
    malformed = "on: [push\njobs:\n  a: {}\n"
    result = scan(git_factory, malformed)
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "FAILED"
    assert not any(n.kind == "workflow_job" for n in result.graph.nodes)

    duplicate = """\
on: [push]
jobs:
  test:
    steps:
      - run: echo 1
      - run: echo 2
  test:
    steps:
      - run: echo 3
"""
    second = scan(git_factory, duplicate)
    assert second.status == "PARTIAL"
    assert second.receipt.files[0].status == "FAILED"


def test_yaml_on_key_remains_event_not_boolean(git_factory):
    content = """\
on: [push, workflow_dispatch]
jobs:
  t:
    steps:
      - run: echo hi
"""
    result = scan(git_factory, content)
    events = {node.name for node in result.graph.nodes if node.kind == "workflow_event"}
    assert events == {"push", "workflow_dispatch"}
    assert result.status == "COMPLETE"


def test_parallel_jobs_are_repeatable_across_contexts_and_revision(git_factory):
    first = scan(git_factory, WORKFLOW)
    second = scan(git_factory, WORKFLOW.replace("echo done", "echo modified"))
    keys_first = {n.qualified_name: n.id for n in first.graph.nodes if n.kind == "workflow_job"}
    keys_second = {n.qualified_name: n.id for n in second.graph.nodes if n.kind == "workflow_job"}
    assert keys_first == keys_second
    assert first.graph.scope.revision != second.graph.scope.revision
    assert {e.id for e in first.graph.edges} == {e.id for e in second.graph.edges}
    assert {e.id for e in first.graph.evidence} != {e.id for e in second.graph.evidence}


def test_workflow_provider_does_not_accept_non_workflow_yaml(git_factory):
    root, sha = git_factory({"docs/memo.yml": "on: [push]\njobs: {}\n"})
    req = ScanRequest(
        repository="example/repo", revision=sha, includes=("docs/*.yml",),
    )
    result = run_scan(req, GitSourceProvider(root))
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "UNSUPPORTED"



def test_condition_without_braces_is_also_not_executed_evidence(git_factory):
    content = """\
on: [push]
jobs:
  test:
    if: github.ref == 'refs/heads/main'
    steps:
      - name: only on branch
        if: success()
        run: echo ok
"""
    result = scan(git_factory, content)
    assert result.status == "PARTIAL"
    assert "JOB_CONDITION_NOT_EVALUATED:test" in result.receipt.files[0].details
    assert any(x.startswith("STEP_CONDITION_NOT_EVALUATED")
               for x in result.receipt.files[0].details)
    assert all(ev.observation_status != "RUNTIME_OBSERVED" for ev in result.graph.evidence)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            """\
on:
  push:
    branches: [main]
    branches: [feature]
jobs:
  test:
    steps:
      - run: echo ok
""",
            id="duplicate-nested-key",
        ),
        pytest.param(
            """\
on: [push]
defaults: &defaults
  shell: bash
jobs:
  test:
    <<: *defaults
    steps:
      - run: echo ok
""",
            id="yaml-merge-key",
        ),
    ],
)
def test_nested_config_yaml_duplicate_key_and_merge_key_fail_closed(git_factory, source):
    result = scan(git_factory, source)
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "FAILED"



def test_exact_source_lines_anchor_event_and_job_declarations(git_factory):
    content = """\
on:
  push:
jobs:
  check:
    steps:
      - run: echo hi
"""
    result = scan(git_factory, content)
    assert result.status == "COMPLETE"
    check = next(n for n in result.graph.nodes if n.kind == "workflow_job")
    assert check.location.start_line == 4
    event_evidence = [
        e for e in result.graph.evidence
        if e.method == "github-actions-static-v0.1" and
        e.source_ref.startswith(".github/workflows/check.yml:2@")
    ]
    assert event_evidence


def test_empty_jobs_or_events_are_not_reported_complete(git_factory):
    missing_events = "on: []\njobs:\n  check:\n    steps:\n      - run: echo ok\n"
    assert scan(git_factory, missing_events).status == "PARTIAL"
    missing_jobs = "on: [push]\njobs: {}\n"
    assert scan(git_factory, missing_jobs).status == "PARTIAL"
