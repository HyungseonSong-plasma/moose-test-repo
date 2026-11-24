# Evolutionary Naming Audit v0.7 — GitHub Actions replay provenance

**Status:** read-only source-backed evidence collection; neither JUnit comparisons nor workflow run success approve a rename, extraction or merge.

## Problem

The v0.6 `ReplayArtifact` stores raw JUnit, an expected digest, and a caller-supplied `run_reference`. These are **not independent provenance**: one actor could supply a matching XML/digest and a fictitious run URL. v0.7 resolves that gap *for the GitHub metadata and artifact archive association* by querying GitHub Actions via its own REST HTTPS endpoints and downloading actual archived XML bytes. It does **not** attest the container, toolchain, test adequacy, or the user's semantic requirements.

## Entry points

- `GitHubActionsRestReader(token=None)` provides bounded, paginated, read-only queries for a workflow run, jobs, artifacts and ZIP bytes. JSON metadata cannot redirect; authorized ZIP downloads may follow HTTPS redirects **without forwarding the GitHub bearer token**. All archive bytes and XML entries are bounded; ZIP traversal, symlinks, duplicates and ambiguous XML are rejected.
- `verify_actions_junit_artifact(repo, exact_sha, run_id, job_name=..., artifact_name=..., workflow_path=..., required_step_names=(...))` independently checks the exact GitHub run's repository, SHA, workflow path, completed/success conclusion, expected successful job and exact-revision verification steps; it then checks that exactly one unexpired artifact belongs to the same run/repository/SHA and extracts its actual ZIP/JUnit content. Never infer an artifact merely from a successful job or an unrelated ZIP.
- `audit_actions_replay(repo, before_sha, after_sha, before_run_id, after_run_id, ...)` is the default two-revision entrypoint; it independently fetches both run/job/archive chains from the same reader rather than trusting caller-produced PASS receipts. A second run-identity read detects run-attempt changes during archive acquisition.
- `compare_actions_junit_replays(before_receipt, after_receipt)` passes SHA-bound **actual source-fetched** XML/digests into canonical `compare_candidate_replay`. It blocks wrong revisions, failed/missing/duplicated tests, source failures, and compares stable test IDs. Its result is `BLOCKED` or `HOLD`, never execution approval.
- An injected reader enables deterministic adversarial unit testing but is explicitly marked `INJECTED_READER`, **not authenticated by GitHub**. Even live REST metadata yields only `GITHUB_METADATA_WITNESSED` for an individual artifact; that status is **not** a behavioral or security PASS.

### Example: a run whose JUnit is already uploaded

```python
from physics_harness.code.verification.naming_actions import (
    verify_actions_junit_artifact, compare_actions_junit_replays,
)

before = verify_actions_junit_artifact(
    "owner/repo", "<before-40hex-sha>", 123456,
    job_name="Harness Code pytest", artifact_name="harness-junit",
    workflow_path=".github/workflows/harness-code.yml",
    required_step_names=("Verify exact source revision",),
)
after = verify_actions_junit_artifact(
    "owner/repo", "<candidate-40hex-sha>", 123457,
    job_name="Harness Code pytest", artifact_name="harness-junit",
    workflow_path=".github/workflows/harness-code.yml",
    required_step_names=("Verify exact source revision",),
)
result = compare_actions_junit_replays(before, after)
assert not result.mutation_approved
```

For private repositories, pass a securely supplied GitHub read token to `GitHubActionsRestReader` and use `source=reader`. Never put tokens in issue comments, reports, exception text or recorded artifacts.

## Real repository control, 2026-11-22

At `moose-test-repo` PR #770 commit `3a8b67147fb59770e02cdf891b3cac150480cf91`:

| Exact run | GitHub workflow | Run / job result | Artifacts |
|---|---|---|---|
| `45081041451` | `.github/workflows/harness-code.yml` | Success / Harness Code pytest success | **None** |
| `45081041440` | `.github/workflows/ci.yml` | Success / validate success | **physics-architecture-census** (`14777176584`), **not JUnit** |

The current Harness workflow checks an exact source revision and runs pytest, but **does not publish JUnit as a GitHub Actions artifact**. Therefore v0.7 must emit `HOLD: JUNIT_ARTIFACT_NOT_UPLOADED` for that run. Reusing the Repository CI architecture census as a test result would be a provenance violation. No workflow was changed in this v0.7 patch; an independently approved, narrowly scoped JUnit upload from the Harness job would be a separate integration step.

The associated source observation and GitHub workflow run identifiers are preserved in `experiments/evolutionary_naming_audit/actions_provenance_v07.json`. This file is an *audit record* of an external read, not a signed attestation or a live replacement for GitHub API reads.

## Explicit missing guarantees and stop conditions

- A GitHub API response authenticates *GitHub's metadata for a run/artifact*, not the executable test environment, its dependencies, a code signing key, or whether a workflow was compromised.
- `run_attempt > 1` leaves `ARTIFACT_RUN_ATTEMPT_NOT_PROVEN` because the artifact list may not identify the exact attempt that produced each retained artifact; do not silently associate the latest attempt with older bytes.
- Tests must be the same relevant public-contract suite, run at the exact baseline/candidate commits with matching toolchain and locked dependencies. A successful pytest exit does not prove unchanged behavior, consumer closure or semantic compatibility.
- External/dynamic consumers, authenticated two-pass semantic review, post-integration revision and rollback are separate blockers. The canonical `NamingSafetyGateReport` remains `mutation_approved=False`.
- No new naming executor, GitHub workflow dispatch or PR merge is introduced.
