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
