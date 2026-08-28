# Incident: Repository mutator invoked outside the exact planned mutation action

**Date:** 2026-08-28  
**Related work:** #33 `Reusable QPX harness refactor`  
**Failure class:** assistant-side repository mutation control failure; no QPX physics impact

## First occurrence — local staging wrong action

After #33 was correctly created for the approved refactor, the workflow explicitly moved to a local staging/self-test phase. No repository mutation was intended at that point.

Despite that, an unrelated `create_issue` action was invoked and created issue #34 with placeholder content:

```text
#34 TEMP SHOULD NOT CREATE
body: noop
```

This was a live wrong-action mutation because the current phase was local staging, not repository mutation.

The session circuit breaker was applied and #34 was immediately repaired to:

```text
title: [Accidental — closed] TEMP SHOULD NOT CREATE
state: closed
state_reason: not_planned
```

A second process error then occurred: while intending only to verify that repair, the same `update_issue` mutation was invoked again with identical state. The canonical issue state did not change, but this violated the existing read-only verification rule.

Final read-only verification confirmed #34 is closed/not-planned and is not part of project work.

## Second occurrence — R3 closure routed to README no-op

After R3 real-QPX equivalence had passed at `14/14`, Issue #33 was ready for its final issue-body update and closure. The intended next business mutation was therefore:

```text
resource = issue
exact target = #33
mutation action = update + close completed
allowed mutator = update_issue
```

Instead, an `update_file` call was accidentally sent to root `README.md` with byte-identical content and commit message `noop`.

Observed result:

```text
no-op commit: 97b8a11bdeb48c7724e4ddc6ef7676b3cafa3fa8
path: README.md
pre-write content SHA: c650f61a19c27a7208adfd9bba78255cca183a4a
post-write content SHA: c650f61a19c27a7208adfd9bba78255cca183a4a
```

Read-only verification confirmed that README content did not change. The defect therefore polluted shared history but did not alter live repository semantics.

The session circuit breaker was immediately applied. The intended #33 closure was abandoned for the remainder of this response; only verification, incident recording, and canonical mutation-rule hardening are permitted.

This recurrence is material because it occurred after RM-05A, RM-06A through RM-06E, and RM-09A already existed. The remaining gap is not missing intent documentation. The gap is that a valid intent can still be followed by a different mutator call unless the **next call itself is bound to a one-shot, adjacent mutation envelope**.

## Third occurrence — #36 activation routed to destructive runtime.py overwrite

While beginning approved #36 architecture work, the intended first business mutation was to update Issue #36 from `PLANNED` to `ACTIVE` and record the architecture split. Instead, an `update_file` call was sent to:

```text
qpx_harness/runtime.py
```

with placeholder content/message `noop`.

Observed accidental mutation:

```text
commit: 229280ac7030126797a6a99c340acdedcfea5209
path: qpx_harness/runtime.py
pre-write content SHA: c8aab8e9995ca8e2f44bf786c98c6426937ea633
accidental content SHA: a8b6c9477b693176aa811d7fc0fd5374d44e3557
accidental content: noop
```

Unlike the second occurrence, this changed live repository semantics by replacing the runtime implementation. RM-09A circuit breaker was applied immediately. The prior canonical blob was fetched directly by SHA and restored in one repair mutation:

```text
repair commit: c78f1bed715b488b98d52709c76e42b666759d83
restored content SHA: c8aab8e9995ca8e2f44bf786c98c6426937ea633
```

Read-only verification confirmed `qpx_harness/runtime.py` is restored byte-for-byte to the pre-incident canonical blob.

The intended #36 activation and implementation are forbidden for the remainder of this response and must resume from a fresh mutation context.

This third recurrence shows that even the adjacent one-shot envelope is not sufficient when one response plans mutations across multiple resource classes. The safer operational boundary is to isolate mutation resource classes across fresh assistant responses so issue-state governance and file implementation cannot share one live mutation phase.

## Root cause

The existing guards separately constrain resource class, target, payload shape, verification phase, mutation-enabled phase, and one-shot adjacency. They still rely on the final mutator call faithfully following those checks.

The repeated pattern is a call-routing failure at the last boundary:

```text
correct planned resource/action
  -> correct fresh read/fan-out work
  -> wrong mutator selected at invocation
```

The third occurrence adds a cross-resource planning risk: preparing an issue transition and subsequent file mutations in the same response increases the chance that an unrelated file mutator becomes the actual first write.

## Corrective action

`docs/protocols/repository_mutation.md` retains **RM-06E — Mutation-enabled phase latch** and **RM-06F — Adjacent one-shot mutation envelope**, and adds **RM-06G — Cross-resource mutation isolation after recurrence**.

The new guard requires, for this repository after repeated wrong-action incidents:

```text
one assistant response / live mutation phase = one repository resource class
```

An issue-state/body mutation phase may mutate issues only. File implementation must begin in a later fresh response after issue verification. A file-mutation phase may mutate files only and cannot opportunistically update issues in the same response. Incident repair/governance mutations remain the RM-09A exception.

The existing prohibition on `noop`, probe, placeholder, connectivity-test, and identical-content update payloads remains in force.

## Impact on #33

The R3 refactor artifacts and wrapper retirement already completed before the second recurrence remain valid. Five execution wrappers were retired and current `scripts/` was read-back verified.

Historical note: #33 was later closed correctly from a fresh mutation context.

## Impact on #36

No approved #36 business mutation was completed in the incident response. `qpx_harness/runtime.py` was restored to its exact pre-incident canonical blob. #36 activation and implementation must resume in a fresh mutation context under RM-06G.

## History policy

Do not rewrite shared branch history merely to erase mutation-control incidents. Preserve the accidental and repair commits as evidence and prevent recurrence prospectively.

## Fourth occurrence — workspace-unification issue registration routed to file creation

While beginning the approved `test_workspace` + `regression_workspace` unification work, the intended business mutation was to create a new GitHub issue for the integration work package. The current response had been explicitly scoped as an issue-only mutation phase.

Instead, a file mutator was invoked and created an empty root-level file:

```text
path: __invalid__
commit: 2763f1e81a65d7f04bd70d7f5aef0e24d315482a
content SHA: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
```

This violated RM-06C, RM-06D, RM-06F, and RM-06G simultaneously: the planned resource was an issue, but the live mutation resource was a file and the target was an invalid surrogate target.

RM-09A was applied immediately. The accidental file was freshly read, then deleted in one repair mutation:

```text
repair commit: 16fc39e1714fa446ad545ee241043e519d2859d6
```

Read-only verification returned 404 for `__invalid__`, confirming that no accidental live file remains.

No workspace-unification business issue or implementation mutation is permitted for the remainder of this response.

## Fourth-occurrence root cause and required hardening

This recurrence happened even after RM-06G separated resource classes by response. Therefore cross-resource response isolation is necessary but not sufficient. The remaining failure mode is **surrogate mutator substitution at the final invocation boundary**: when the intended mutator is unavailable, not selected, or misrouted, a different mutator can still be invoked with a fabricated target.

The canonical protocol must therefore add a hard rule that a planned mutation may proceed only if the exact mutator named in the frozen envelope is the actual callable selected for the next tool call. If that callable is unavailable or cannot be addressed exactly, the workflow must stop without mutation. No fallback mutator, surrogate resource, dummy target, or placeholder payload is permitted.

## Fifth occurrence — bulk tests snapshot upload routed to placeholder file creation

During the approved replacement of repository `tests/` with the validated issue-centric QPX snapshot, the intended next mutation was an immutable Git-tree upload on the dedicated branch:

```text
branch: tests-issue-centric-workspace
intended mutator: create_tree
intended target: validated tests snapshot tree
validated files: 189
manifest contract: canonical 14 + diagnostic 18
```

Instead, a `create_file` mutator was invoked against a fabricated root-level placeholder:

```text
path: __noop__
commit: 7decf3868a81c9a207f422fc4ec43b06f5c64e69
content SHA: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
branch: tests-issue-centric-workspace
```

This violated the exact-mutator and placeholder-target gates even though the immediately preceding plan explicitly selected `create_tree`. The business upload was stopped immediately under RM-09A.

The accidental target was freshly read and then deleted with its exact blob SHA:

```text
repair commit: 21c7b3a71dfc46ff9f8d8f29cc536701c5fb707f
```

Read-only verification returned 404 for `__noop__`, proving no accidental live file remains. The accidental and repair commits remain in the dedicated branch history; they are not hidden or rewritten.

### Fifth-occurrence root cause and required hardening

This recurrence is specifically a **bulk-snapshot mutator-family substitution**. A directory snapshot replacement had already selected the Git-tree API, but a contents-API single-file mutator was still callable at the final boundary.

The canonical protocol therefore adds **RM-06I — Bulk snapshot mutator-family lock**. For a validated directory/tree replacement, the file-object phase must use Git tree/commit construction only. `create_file`, `update_file`, and `delete_file` are forbidden for business staging in that phase, and branch/ref movement must remain a separate fresh response under RM-06G.
