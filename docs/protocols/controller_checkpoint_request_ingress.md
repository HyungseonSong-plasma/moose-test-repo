# Request-file bootstrap of Controller contract qualification — candidate

Reuse the existing request-file pattern without changing the read-only Harness
scan workflow or its shared request branch. No additional standing Workflow is
needed: add a narrowly filtered `workflow_run` entrypoint to the existing
Controller Checkpoint Contract CI. It invokes the existing Samuel runtime using
an ephemeral repository-scoped `GITHUB_TOKEN`; no PAT and no new provider.

## First operation only: isolated qualification request PR

After reviewed ingress deployment on main, an authorized caller creates a fresh
Draft PR from that exact main, branch `issue-888-checkpoint-qualification-<12 lowercase hex>`.
Its sole commit must have exactly one parent (current main) and add only
`automation/controller-requests/checkpoint-contract.json`. The caller uses the
registered branch/file/PR creation routes and existing prewrite/identity/blocker
gates. This is not a workload Controller's state branch and does not weaken its
independent PR requirement. The dedicated one-time qualification PR is used to
bootstrap the shared contract; no lane writes to it. The request is data only:

```json
{
  "schema_version": 1,
  "expected_main_sha": "<fresh deployed main SHA>",
  "expected_contract_sha256": "<SHA256 of deployed contract file bytes>",
  "expected_samuel_pin": "<exact deployed central pin>"
}
```

Repository CI completes at the exact request HEAD. The existing contract
workflow's ingress job runs on the default branch, checks out only that source,
fetches the exact central revision as existing Repository CI does, and verifies
repository/owner IDs, workflow identity, successful CI, unique open Draft PR,
commit parents and changed path, Git blob hash and strict request body, complete
bounded run inventories, and fresh main/PR refs. Arbitrary workflow/inputs/ref,
PR code execution, extra paths, contents write, and fork requests are forbidden.
It calls `dispatch_contract` (Samuel `dispatch_workflow`) for the existing
qualification workflow at `main`, with correlation derived from the request HEAD.
Preserve the original Samuel dispatch receipt (or explicit unknown outcome) in
an ingress artifact. The existing consumer observes the child with Samuel
`observe_dispatch_once` and verifies its qualification receipt; that integration
must be exercised on hosted CI before use. Manual dispatch remains unchanged.

## Limits

Concurrency is request-specific, not a global lock. Repeated runs, missing
correlation metadata, ambiguous or incomplete inventory, stale source, and
already visible child runs stop. The pre-dispatch local receipt is created
exclusively; a lost response is reconciled read-only, never blindly replayed.
The local marker is not a durable cross-run lock and eventual consistency can
make observations incomplete. Do not claim distributed exactly-once delivery.
Enumeration is deliberately limited to 100 results per query; larger inventories
HOLD until a separately verified pagination strategy is available. Actual GitHub
workflow_run metadata, permissions, token availability, and artifact retention
remain to qualify. No remote dispatch or writes were performed by this candidate.
The qualification receipt includes hashes of ingress source, entrypoint and tests;
old receipts become invalid when deployed. This does not certify live Connector
CAS, bypass a prior denial, or authorize production checkpoint publication.
The five existing workload reservations remain paused. A separate fresh Work
Identity/approved history evidence binding is necessary for remote publication;
prior #911-only owner decision is not automatically generalized.
