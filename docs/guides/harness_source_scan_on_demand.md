# Harness Code source scan — on-demand execution

**Owner:** Harness Code / [#758](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/758).
The scan is read-only. It collects source facts, not safe-delete decisions or
runtime/semantic-compatibility proofs.

The canonical workflow is `.github/workflows/harness-code-scan.yml`.
It reuses the existing `GitSourceProvider → run_scan → GraphSnapshot +
EvidenceReceipt + VerificationReceipt`; no second diagnostics engine is
implemented.

## Two deliberate execution routes

### A. Human: GitHub Actions UI

After the workflow is integrated into `main`:

1. Open **Actions → Harness Code Source Scan → Run workflow**.
2. Choose the source branch or revision in the standard dispatch selector.
3. Set include/exclude globs, collectors and budgets; select **Run**. For current Code and metrics sources, explicitly set `physics_harness/code/*.py,libs/code_lucidity/*.py`: the existing UI default still contains the retired `libs/hu` path.

This route uses `workflow_dispatch`. No ordinary `main` push, PR update or
schedule starts it.

### B. ChatGPT: bounded request on a dedicated GitHub branch

The connected GitHub app can create/update a repository file, but may not
expose GitHub's `workflow_dispatch` POST API. To let ChatGPT execute the
same workflow without credentials, browser login or a persistent external
controller, the workflow additionally accepts **only** a push to:

- **Branch:** `issue-758-harness-scan-dispatch`
- **Changed file:** `automation/harness-scan/request.json`

No other branch or changed path matches. This push is an explicit scan request
submitted by ChatGPT, **not** an automatic check on code changes. The workflow
uses `contents: read`, verifies the exact source SHA and never commits back.

**Initial provisioning:** the dedicated `issue-758-harness-scan-dispatch`
branch and its request file were already created during the successful
[ChatGPT end-to-end test](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44958694044).
Reuse this existing branch for subsequent requests. If the branch is ever
absent, provision it only under the repository mutation policy using the
currently approved workflow revision. The request schema is:

```json
{
  "schema": "harness.source_scan.v1",
  "request_id": "issue758-g0-002",
  "source_sha": "<exact-40-hex-main-commit-sha>",
  "includes": ["physics_harness/code/*.py", "libs/code_lucidity/*.py"],
  "excludes": [],
  "collectors": ["python_ast"],
  "max_files": 500,
  "max_bytes": 20000000,
  "max_seconds": 240
}
```

For later runs, retrieve `request.json` from `issue-758-harness-scan-dispatch` and
update that same file with its **current blob SHA**. Use a new `request_id`
on every deliberately requested run (including a repeat of an older source
SHA). Do not add new branches or tags per run. Fetch the desired source SHA
immediately before each request; never confuse the request **commit SHA**
with the separately pinned **source SHA**.

Accepted collectors: `python_ast`, `workflow`, `cpp`, `moose_input`, `json`.
For JSON documents select `json` and matching `.json` globs explicitly. The Python/HIT/JSON collectors report file-reference candidates; the source scan does not automatically run the separate exact-inventory [`resolve_file_references`](../../physics_harness/code/analysis/README.md) analysis. Markdown and shell are not implemented source collectors.
A request may select multiple collectors and a scoped union of file patterns.
Maximum budgets: 1,500 files, 100,000,000 tracked-source bytes and 600
seconds. `ScanRequest` and the existing collectors still validate scopes and
leave unsupported or budget-exceeded sources `PARTIAL`; a status of
`COMPLETE` applies only to the requested and supported surfaces.

The workflow run uses a `push` event for route B; correlate it using the
request-file commit SHA, request ID and source SHA in the exported summary.
If the connector cannot create/update the dispatch branch or the workflow
is not registered on that branch, **report the blocker**; do not spoof a
successful run.

## Evidence and readback

Every attempt uploads a 30-day GitHub Actions Artifact named
`harness-source-scan-<run_id>-<run_attempt>`, containing:

- `request.json` — exact source revision, declared scope, collectors, budget
- `graph.json` — canonical source graph
- `evidence-receipt.json` — file coverage, Blob IDs, unresolved conditions
- `verification-receipt.json` — source provenance verification
- `summary.json` — exact source/request identity, graph counts, statuses
- `execution-error.json` — if an error occurs before normal completion

Actions Job Summary shows source SHA, scope, coverage and verification status.
Do **not** treat a successful Actions Job as `COMPLETE` when the report says
`PARTIAL`/`UNVERIFIED`. Neither a VERIFIED source artifact nor a static
source scan proves global consumer closure, runtime semantics or permission
for code/Tag/branch deletion.

The repository Workflow Surface Guard registers the two allowed events and
rejects broad push paths, other branches and PR/schedule activation.
