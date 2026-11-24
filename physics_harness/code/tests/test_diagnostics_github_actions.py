"""GitHub Actions runtime provider: attempt-pinned, fail-closed observations."""

from copy import deepcopy

import pytest

from physics_harness.code.diagnostics import (
    FactBatch, GitHubActionsRunProvider, GitSourceProvider,
    GraphAssembler, ScanRequest, run_scan,
)


RUN_ID = 456
ATTEMPT = 2
BASE = (
    "https://api.github.com/repos/example/repo"
    f"/actions/runs/{RUN_ID}/attempts/{ATTEMPT}"
)
YAML = "on: [push]\njobs:\n  check:\n    steps:\n      - run: echo ok\n"


def source(git_factory):
    root, sha = git_factory({".github/workflows/ci.yml": YAML})
    request = ScanRequest(
        repository="example/repo", revision=sha,
        includes=(".github/workflows/*.yml",),
    )
    return request, run_scan(request, GitSourceProvider(root))


def payloads(sha, *, split=False):
    run = {
        "id": RUN_ID, "run_attempt": ATTEMPT, "head_sha": sha,
        "status": "completed", "conclusion": "success",
        "html_url": f"https://github.com/example/repo/actions/runs/{RUN_ID}",
        "updated_at": "2026-11-19T00:10:00Z",
        "created_at": "2026-11-19T00:05:00Z",
        "event": "push", "path": ".github/workflows/ci.yml",
    }
    jobs = [
        {
            "id": 900, "run_id": RUN_ID, "head_sha": sha,
            "name": "check", "status": "completed", "conclusion": "failure",
            "html_url": "https://github.com/example/repo/actions/runs/456/job/900",
            "steps": [
                {"number": 1, "name": "checkout", "status": "completed",
                 "conclusion": "success"},
                {"number": 2, "name": "validate", "status": "completed",
                 "conclusion": "failure"},
            ],
        },
        {
            "id": 901, "run_id": RUN_ID, "head_sha": sha,
            "name": "optional", "status": "completed", "conclusion": "skipped",
            "html_url": "https://github.com/example/repo/actions/runs/456/job/901",
            "steps": [],
        },
    ]
    pages = {
        f"{BASE}/jobs?per_page=100&page=1": {
            "total_count": 2, "jobs": jobs[:1] if split else jobs,
        },
        f"{BASE}/jobs?per_page=100&page=2": {
            "total_count": 2, "jobs": jobs[1:],
        },
    }
    return run, pages


def client(run, pages):
    def get(url):
        if url == BASE:
            return deepcopy(run)
        return deepcopy(pages[url])
    return get


def test_runtime_provider_keeps_job_and_step_status_independent(git_factory):
    request, source_result = source(git_factory)
    run, pages = payloads(request.revision)
    observed = GitHubActionsRunProvider(client(run, pages)).collect_run(
        request, RUN_ID, ATTEMPT,
    )
    assert observed.status == "COMPLETE"
    combined = GraphAssembler().assemble(
        request,
        (
            FactBatch(
                nodes=source_result.graph.nodes,
                edges=source_result.graph.edges,
                evidence=source_result.graph.evidence,
            ),
            observed.batch,
        ),
        source_result.receipt,
    )
    assert combined.status == "COMPLETE"
    jobs = [n for n in combined.graph.nodes if n.kind == "github_actions_job"]
    assert {j.attributes["conclusion"] for j in jobs} == {"failure", "skipped"}
    run_node = next(n for n in combined.graph.nodes
                    if n.kind == "github_actions_run_attempt")
    assert run_node.attributes["conclusion"] == "success"
    assert not combined.graph.claims
    assert {e.relation for e in combined.graph.edges} >= {
        "OBSERVED_JOB", "OBSERVED_STEP",
    }
    runtime = [e for e in combined.graph.evidence
               if e.observation_status == "RUNTIME_OBSERVED"]
    assert len(runtime) == 5
    assert all(e.attributes["source_sha"] == request.revision for e in runtime)
    assert all(e.attributes["run_id"] == RUN_ID for e in runtime)
    assert all(e.attributes["attempt"] == ATTEMPT for e in runtime)


def test_runtime_pages_are_scoped_and_prove_complete_pagination(git_factory):
    request, _ = source(git_factory)
    run, pages = payloads(request.revision, split=True)
    result = GitHubActionsRunProvider(client(run, pages)).collect_run(
        request, RUN_ID, ATTEMPT,
    )
    assert result.status == "COMPLETE"
    run_node = next(n for n in result.batch.nodes
                    if n.kind == "github_actions_run_attempt")
    assert run_node.attributes["pages_read"] == 2
    assert run_node.attributes["job_total_count"] == 2


def test_truncated_pagination_is_partial_and_never_pass(git_factory):
    request, baseline = source(git_factory)
    run, pages = payloads(request.revision, split=True)
    result = GitHubActionsRunProvider(
        client(run, pages), max_pages=1,
    ).collect_run(request, RUN_ID, ATTEMPT)
    assert result.status == "PARTIAL"
    assert "JOB_PAGINATION_INCOMPLETE" in result.batch.unresolved
    combined = GraphAssembler().assemble(
        request,
        (
            FactBatch(nodes=baseline.graph.nodes, edges=baseline.graph.edges,
                      evidence=baseline.graph.evidence),
            result.batch,
        ),
        baseline.receipt,
    )
    assert combined.status == "PARTIAL"


def test_cross_head_and_cross_attempt_observations_are_rejected(git_factory):
    request, _ = source(git_factory)
    run, pages = payloads(request.revision)
    wrong_head = deepcopy(run)
    wrong_head["head_sha"] = "0" * 40
    with pytest.raises(ValueError, match="CROSS_HEAD_RUNTIME_EVIDENCE"):
        GitHubActionsRunProvider(client(wrong_head, pages)).collect_run(
            request, RUN_ID, ATTEMPT,
        )
    wrong_attempt = deepcopy(run)
    wrong_attempt["run_attempt"] = 1
    with pytest.raises(ValueError, match="ACTIONS_RUN_ATTEMPT_MISMATCH"):
        GitHubActionsRunProvider(client(wrong_attempt, pages)).collect_run(
            request, RUN_ID, ATTEMPT,
        )
    bad_jobs = deepcopy(pages)
    bad_jobs[f"{BASE}/jobs?per_page=100&page=1"]["jobs"][0]["head_sha"] = "0" * 40
    with pytest.raises(ValueError, match="CROSS_HEAD_ACTIONS_JOB"):
        GitHubActionsRunProvider(client(run, bad_jobs)).collect_run(
            request, RUN_ID, ATTEMPT,
        )


def test_api_unavailable_results_in_failed_unresolved_receipt(git_factory):
    request, _ = source(git_factory)

    def denied(url):
        raise PermissionError("private token omitted")

    result = GitHubActionsRunProvider(denied).collect_run(
        request, RUN_ID, ATTEMPT,
    )
    assert result.status == "FAILED"
    assert "ACTIONS_RUN_METADATA_UNAVAILABLE" in result.batch.unresolved
    assert not result.batch.evidence
    assert not result.batch.nodes
    assert result.errors == ("RUN_FETCH_FAILED:PermissionError",)


def test_mid_scan_run_mutation_is_partial(git_factory):
    request, _ = source(git_factory)
    run, pages = payloads(request.revision)
    count = 0

    def mutation(url):
        nonlocal count
        if url == BASE:
            count += 1
            state = deepcopy(run)
            if count == 2:
                state["updated_at"] = "2026-11-19T00:11:00Z"
            return state
        return deepcopy(pages[url])

    result = GitHubActionsRunProvider(mutation).collect_run(
        request, RUN_ID, ATTEMPT,
    )
    assert result.status == "PARTIAL"
    assert "RUN_CHANGED_DURING_OBSERVATION" in result.batch.unresolved


def test_incomplete_job_or_step_does_not_become_pass(git_factory):
    request, _ = source(git_factory)
    run, pages = payloads(request.revision)
    run["status"] = "in_progress"
    run["conclusion"] = None
    pages[f"{BASE}/jobs?per_page=100&page=1"]["jobs"][0]["steps"][1]["status"] = "in_progress"
    pages[f"{BASE}/jobs?per_page=100&page=1"]["jobs"][0]["steps"][1]["conclusion"] = None
    result = GitHubActionsRunProvider(client(run, pages)).collect_run(
        request, RUN_ID, ATTEMPT,
    )
    assert result.status == "PARTIAL"
    assert "RUN_NOT_COMPLETED" in result.batch.unresolved
    assert "RUN_CONCLUSION_UNKNOWN" in result.batch.unresolved
    assert "STEP_NOT_COMPLETED:900:2" in result.batch.unresolved


def test_bad_run_identity_or_params_are_rejected(git_factory):
    request, _ = source(git_factory)
    run, pages = payloads(request.revision)
    observer = GitHubActionsRunProvider(client(run, pages))
    for invalid in (0, True, "456"):
        with pytest.raises(ValueError, match="INVALID_RUN_ID"):
            observer.collect_run(request, invalid, ATTEMPT)
    wrong_run = deepcopy(run)
    wrong_run["id"] = 12
    with pytest.raises(ValueError, match="ACTIONS_RUN_ATTEMPT_MISMATCH"):
        GitHubActionsRunProvider(client(wrong_run, pages)).collect_run(
            request, RUN_ID, ATTEMPT,
        )
