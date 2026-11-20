# CI Retention Audit v0.2 — live checks vs historical evidence

Issue: #752. PR implementation is intentionally restricted to CI ownership,
execution frequency and dedicated audit controls; Physics source and P3/P4
scientific authorization are unchanged.

## Execution ownership

| Scope | Previous behavior | Current behavior |
|---|---|---|
| Repository Integration Contract | Required, single core validate | Unchanged |
| Physics Code Validation | Full pytest and source guards | Remains automatic |
| Wave1-E merged CI and ZIP receipt | Every code PR | Manual `Physics Legacy Audit` |
| Issue402 S6 417/941 historical reference receipt | Every code PR | Manual `Physics Legacy Audit` |
| Issue402 legacy-symbol inventory | Every code PR | Manual `Physics Legacy Audit` |
| Issue402 JSON-rate / ideal-gas / CORE four / reaction-material P0 | Four extra CI jobs repeating many tests | Manual exact-source reproduction; live invariants consolidated into Physics Code Validation |
| Group A and ARCH replay release/authorization controls | Automatic | Remain automatic until separately approved impact/authority review |
| Physics Native P1/P2 and Boltzmann C++ | Automatic for native-relevant PR | Unchanged |

Invoke `Physics Legacy Audit` via GitHub Actions, select exactly one
`audit` choice and specify the branch/ref to audit. The moved job uses the
chosen ref's exact `github.sha` and retains its original commands, source
checks, historical mutation tests, artifact policy, and evidence output.
This workflow has **no** push/PR triggers and cannot issue a scientific PASS.

The automatic `physics_code_validate` still runs `python -m pytest -q`
for all `tests/` except the five FDEG suites executed separately. The
old Issue402 P0 jobs each repeated test paths covered by this collection.
Their non-pytest source invariants are represented by the
`Verify current-source P0 invariants formerly duplicated in Issue jobs`
step, which checks Stage5 reaction ownership, JSON-rate negative controls,
energy projection and initial-composition legacy absence. Existing electron
impact and energy implementation guards remain separate active steps.

## Guarantees

- No deliberate test source deletion or modification.
- Historical ledger data and immutable receipt identities remain historical.
- The current source checker cannot be bypassed by an absent historical
  artifact. Historical receipt checks are still available on demand.
- Job and step ownership is checked by `repository_ci_scope.py`, including
  negative tests for accidental automatic audit execution, missing selector
  and deletion of a retained active Physics invariant.
- `workflow_surface_guard.py` requires the new audit workflow to be manual.
- No P3/P4 run or science acceptance is authorized.

## Corrected contract terminology — lifecycle over discovery

The authoritative definitions and complete job-by-job reclassification are in
[Contract Lifecycle v0.1](CONTRACT_LIFECYCLE_V01.md), issue #754.

- **Static Contract**: a permanent repository invariant independent of which
  development Issue or PR is currently active. It never expires with task
  completion.
- **Dynamic Contract**: a temporary verification and acceptance gate needed
  for a **specific development task**. It is active only until that task has
  completed its required verification, scoped acceptance and evidence custody.
  It must then be removed from the active CI/contracts.
- **Regression tests and evidence receipts** are not themselves separate
  contract lifetimes. Keep valuable behavior tests; archive accepted receipts.

This supersedes the earlier wording that equated "dynamic contracts" with
auto-discovered `ContractProvider` declarations. An optional code-discovery
mechanism may implement either type, but **does not determine the type**.
Likewise, `repository_ci_scope_v1.json` is a temporary migration inventory,
not a permanent list of mandatory historical jobs.

The seven `Physics Legacy Audit` jobs moved by this PR are an *intermediate
containment step*, not completion of Dynamic Contract retirement. Do not
perpetually retain obsolete one-shot Guards in manual CI after their accepted
scope is verified and archived. Retire those contracts separately, preserving
useful generic tests and historical evidence.
