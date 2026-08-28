# Incident: Repository no-op and wrong-action mutations

**Incident ID:** `INC-REPO-MUTATION-001`  
**Status:** OPEN / ACTIVE PROCESS INCIDENT — session circuit breaker required  
**Associated work:** Issue #25 `Repository mutation safety + stale-state synchronization protocol`  
**Failure class:** assistant-side repository/governance mutation; no QPX physics impact

## Symptom

Two related repository-mutation defects were originally observed:

1. A README synchronization operation issued multiple `update_file` calls after the first successful semantic update. The later calls wrote identical content/blob state and created no-op commits.
2. During the cleanup/retrospective, a wrong mutator was invoked and created a placeholder root file `__noop__`; it was immediately removed in the next commit.
3. After #2 closed and #16 became ACTIVE, #17 still contained stale current-state wording (`#2 ACTIVE`, `#16 BLOCKED`) until explicitly repaired.

The no-op commit sequence does not change repository content, but it pollutes history and weakens trust in mutation discipline. The placeholder create/delete pairs temporarily changed repository contents and required corrective cleanup.

## Recurrence after first process fix

A recurrence occurred immediately after `docs/protocols/repository_mutation.md` had been introduced. While resuming #16, the intended repository mutation was an **issue-body update to #16**, but an `update_file` call was accidentally issued against `README.md` with content identical to the fetched README state.

Observed result:

```text
commit: 2be5f419cef50f6190411110df43532ffc7d50c4
returned content SHA: c650f61a19c27a7208adfd9bba78255cca183a4a
pre-write README content SHA: c650f61a19c27a7208adfd9bba78255cca183a4a
```

This was another no-op history-polluting commit. No live repository content changed.

## Second wrong-action recurrence during #16 decomposition

A structural wrong-action recurrence occurred on 2026-08-27 while decomposing #16 after its EVR/RWR stop condition.

The intended next mutation was to create a **GitHub successor issue**, but the selected mutator was `create_file` and a placeholder root path `__noop__` was supplied. This created an unintended repository file:

```text
create commit: dfa6aeff28a5b91fedc0b2f66440544a05750fb1
path: __noop__
content: x
```

The accidental live state was immediately repaired after a fresh read of the created file:

```text
file blob: c1b0730e0133447badcfd47fd144e254807b06e1
repair commit: 9f7f01ce3984c8b74041ace322b850c1bd2817b9
post-repair: __noop__ -> 404 / absent
```

No intended issue/dependency mutation was performed during this faulty step.

## Immediate third recurrence after RM-06C hardening

After recording the `__noop__` recurrence and adding RM-06C create-target attestation, the same session attempted to resume the exact planned successor-issue creation. Despite the strengthened written guard, a wrong `create_file` mutator was again selected and created another unintended root placeholder:

```text
create commit: 1a77c0441d93e1367072c6ca3f605e75573732b2
path: dummy
content: x
```

The file was immediately fetched and removed:

```text
file blob: c1b0730e0133447badcfd47fd144e254807b06e1
repair commit: e7aee1519ec9cff77de9c6be96ace7f87cb95988
post-repair: dummy -> 404 / absent
```

This recurrence proves that additional written call-boundary attestation alone is not sufficient inside a session once a wrong-action mutation has already occurred. The safe response must therefore include a **session-level mutation circuit breaker**: after one wrong-action repository mutation, only minimal repair and governance-record updates are permitted in that same session/response; intended business mutations must be deferred to a fresh mutation context.

## Fourth recurrence during #29 SIGSEGV diagnosis

A further wrong-action recurrence occurred on 2026-08-27 while the intended mutation was an **issue-body update to #29** after diagnosing a Q0 runtime SIGSEGV. The canonical mutation protocol and issue target had already been freshly read, but the selected mutator was nevertheless `update_file` against root path `dummy` with empty content.

Observed accidental mutation:

```text
wrong-action commit: c6bb8bc621155dcc1413b4808a5e83d4bafa364b
path: dummy
content: <empty>
blob: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
```

The session circuit breaker was then applied correctly: the intended #29 business mutation was abandoned, the accidental target was freshly read, and only minimal repair/governance recording continued.

Repair:

```text
repair commit: c0f25059baf078df4dae0db2f60f49e45f64f077
post-repair target: dummy absent
```

This recurrence is especially significant because it happened **after** RM-06A/RM-06C/RM-09A existed and after the correct issue intent had been identified. The remaining failure mode is therefore not missing intent documentation; it is failure to enforce the frozen resource class at the actual mutator-call boundary.

## Fifth recurrence during #32 artifact publication

A new no-op/wrong-action recurrence occurred on 2026-08-28 while publishing the Issue #32 performance-diagnostic artifacts.

The file `tests/r32_performance/test_r32_analyze_profile.py` had already been created successfully. The next intended operation was **post-write verification/read only**, but `update_file` was mistakenly invoked on the same path with byte-identical content.

Observed result:

```text
no-op commit: 2940bf7bac5bbab858eeb595c2424c2ad6824cce
path: tests/r32_performance/test_r32_analyze_profile.py
pre-write blob SHA: 50844d7d77da25a4a049a1a29c33cd004efb2bd2
returned content SHA: 50844d7d77da25a4a049a1a29c33cd004efb2bd2
post-write blob SHA: 50844d7d77da25a4a049a1a29c33cd004efb2bd2
```

No live repository content changed, but shared history was polluted. The intended Issue #32 body update was abandoned for the remainder of the response and the session circuit breaker was applied.

This recurrence identifies a distinct enforcement gap: resource-class and target guards are insufficient when the wrong action is a mutator against the **correct resource and correct target** during what should have been a read-only verification phase. Post-write verification itself must therefore be action-locked to read/fetch operations.

## Root-cause analysis

### RC-1 — Missing pre-write semantic-diff gate
The original write path checked neither “does the intended replacement differ from the fetched current content?” nor “is the returned content/blob SHA already the intended state?” before issuing another write.

### RC-2 — Missing single-write stop condition
There was no hard rule that a successful mutation to a target ends that target's write phase until a fresh read proves another semantic change is required.

### RC-3 — Mutation action was not bound to an explicit intent tuple
A structural `create_file` action could be invoked even though the intended work was issue/protocol synchronization.

### RC-4 — Dependency fan-out was not treated as part of a state transition
#17 retained stale dependency wording after an upstream lifecycle change until explicitly repaired.

### RC-5 — Intent was not frozen to the concrete tool recipient
A nearby/previously loaded file mutator could still be selected even though the intended resource was an issue.

### RC-6 — Structural create target was not attested against the pre-mutation plan
For server-assigned resources such as issues, the exact pre-create identity was not treated as binding strongly enough, permitting invented surrogate targets.

### RC-7 — No session-level circuit breaker after a structural wrong-action mutation
After the first `__noop__` recurrence had already demonstrated a live wrong-action defect in the current session, the workflow resumed intended repository mutation after documenting a stronger rule. The same wrong resource-class mutation recurred immediately as `dummy`.

Consequence: once a session has demonstrated wrong-action routing, written guard updates in that same session are insufficient evidence that subsequent business mutations are safe.

### RC-8 — Frozen intent was not enforced as a payload-shape invariant
During the fourth recurrence the intended resource was already known to be an issue, yet a payload containing a repository file `path` and file-content fields was still allowed to reach a mutator. A frozen issue intent must make any file-mutator payload shape itself a hard pre-call failure, independent of semantic intent notes.

### RC-9 — Post-write verification was not action-locked to read-only tools
During the fifth recurrence the resource class and target were both correct, so resource-class/target guards did not prevent an `update_file` call. The actual phase intent was verification, not mutation. Verification must therefore have its own read-only action lock that forbids every mutator regardless of target correctness.

## Corrective action

Canonical procedure:

```text
docs/protocols/repository_mutation.md
```

The process hardening sequence now includes:

```text
RM-05A Post-write verification read-only lock
RM-06A Mutator recipient freeze
RM-06B File byte-state guard
RM-06C Create-action exact-target attestation
RM-06D Resource-class payload-shape lock
RM-09A Session mutation circuit breaker after wrong-action recurrence
```

The circuit breaker requires:

```text
wrong-action mutation occurs
  -> stop intended/business mutations for the remainder of the session/response
  -> perform only minimal live-state repair
  -> record/update the incident and canonical prevention rule
  -> verify accidental targets are absent or content-identical/restored
  -> resume intended repository mutations only in a fresh mutation context
```

This rule deliberately prefers incomplete repository synchronization over another potentially destructive or history-polluting mutation.

## Verification

The process fix is considered active when all of the following hold:

```text
__noop__ absent from repository root
dummy absent from repository root
repository-mutation protocol exists and is routed from PROTOCOL_INDEX.md
post-write verification uses read/fetch actions only; no mutator is permitted in VERIFY mode
no second write is issued to a target after success unless a fresh read proves a new semantic diff
issue intent cannot invoke a file mutator without failing RM-06A/RM-06D
update_file cannot run on byte-identical fetched/intended content under RM-06B
create_* cannot run unless the exact planned target identity is attested at the call boundary
no invented placeholder target can substitute for a server-assigned create target
a wrong-action mutation trips the session circuit breaker before any further intended/business mutation
```

## History policy

Do not rewrite shared branch history merely to erase these commits. Preserve the incident and recurrence as evidence and prevent recurrence prospectively.
