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

## Sixth recurrence during Issue48 FD legacy retirement

On 2026-08-31, the intended next mutation was a **file deletion** of `qpx_harness/jacobian_fd_reference_audit.py` after WP29 had established zero Python and execution consumers. The target file was freshly read with blob SHA `fde54c7663e2861238f3dcefc8b70c9c1a11433c`, but the selected mutator was `update_ref` against branch `refactor/qpx-harness-generality` instead of `delete_file`.

Observed call/result:

```text
intended action: delete_file qpx_harness/jacobian_fd_reference_audit.py
wrong action: update_ref refactor/qpx-harness-generality -> 3049650acfee8b47c69ac14fd61d930f3e537db3
result: success=true
post-call branch HEAD: 3049650acfee8b47c69ac14fd61d930f3e537db3
```

The branch already pointed to that exact commit, so the wrong action produced no semantic state change and no new commit. The intended legacy-file deletion was abandoned for the remainder of the response under RM-09A.

This recurrence shows that resource-class and payload guards still need an explicit **structural-action opcode lock**: once an action is frozen as `delete existing file`, every branch/ref mutator must be categorically forbidden even if it targets the correct branch and results in a no-op.

## Seventh recurrence during Issue50 state synchronization

On 2026-09-01, after completing the read-only Stats builder/mapping characterization, the intended next mutation was an **issue-body update to Issue #50**. The issue was freshly read, but the selected mutator was `update_file` and an invented root path `__INVALID__` with empty content was supplied instead of calling `update_issue`.

Observed accidental mutation:

```text
intended action: update_issue #50
wrong action: update_file __INVALID__
wrong-action commit: 60cd522fbc22a68343fd14243d9a7007be90b204
path: __INVALID__
content: <empty>
blob: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
```

The accidental target was immediately fetched and removed under the session circuit breaker:

```text
repair commit: cb190dcb7eaa9e1dd9b643a9f8dc42a8c1ac1993
post-repair: __INVALID__ -> 404 / absent
```

The intended Issue #50 business mutation was abandoned for the remainder of the response. This is not a new semantic failure class: RM-06A, RM-06D, RM-06F, RM-06G, RM-06H, and RM-09A already forbid exactly this resource-class/payload/target mismatch. The recurrence therefore reflects enforcement failure at the actual tool-call boundary rather than a missing canonical rule; no duplicate mutation rule is added.

## Eighth recurrence during Issue51 cross-chat handoff

On 2026-09-01, the intended mutation was an **issue-body update to Issue #51** so a fresh chat could resume from the exact state `Cut E2 implemented / P0 validation pending`. `OPERATING_CORE.md`, Issue #51, `PROTOCOL_INDEX.md`, `rule_working_set.md`, `repository_mutation.md`, and `BOOTSTRAP.md` had been read, and Issue #51 was freshly read immediately before the planned write. Despite that, the selected mutator was again `update_file` against the invented root path `__INVALID__` with empty content instead of `update_issue`.

Observed accidental mutation:

```text
intended action: update_issue #51
wrong action: update_file __INVALID__
wrong-action commit: 96b02e5a1a2fe357aec63c123cac877555089348
path: __INVALID__
content: <empty>
blob: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
```

The accidental file was freshly read and removed immediately under RM-09A:

```text
repair commit: a2cf97bbf87d40d4cc2678637973433fea968451
post-repair: __INVALID__ -> 404 / absent
```

The intended Issue #51 business mutation was abandoned for the remainder of the response/session. This is the same already-covered resource-class/payload/target mismatch as the seventh recurrence; RM-06A, RM-06D, RM-06F, RM-06G, RM-06H, and RM-09A already forbid it. Therefore no duplicate semantic mutation rule is added. The recurrence remains enforcement failure at the actual tool-call boundary, not a new QPX technical or physics failure class.

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

### RC-10 — Structural mutation action was not locked independently from resource/target
During the sixth recurrence the intended resource and target were known and freshly read, but a branch/ref action was selected instead of the frozen file-delete opcode. Structural mutation safety must therefore bind the **exact action family** (`delete_file`, `update_ref`, etc.) in addition to resource class and target identity.

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
RM-06J Structural-action opcode lock
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
file-delete intent can invoke only delete_file with the freshly fetched path/blob SHA; branch/ref mutation is forbidden
a wrong-action mutation trips the session circuit breaker before any further intended/business mutation
```

## History policy

Do not rewrite shared branch history merely to erase these commits. Preserve the incident and recurrence as evidence and prevent recurrence prospectively.
