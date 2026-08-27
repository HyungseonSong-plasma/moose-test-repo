# Incident: Repository no-op and wrong-action mutations

**Incident ID:** `INC-REPO-MUTATION-001`  
**Status:** CLOSED / PROCESS FIXED  
**Associated work:** Issue #25 `Repository mutation safety + stale-state synchronization protocol`  
**Failure class:** assistant-side repository/governance mutation; no QPX physics impact

## Symptom

Two related repository-mutation defects were observed:

1. A README synchronization operation issued multiple `update_file` calls after the first successful semantic update. The later calls wrote identical content/blob state and created no-op commits.
2. During the cleanup/retrospective, a wrong mutator was invoked and created a placeholder root file `__noop__`; it was immediately removed in the next commit.
3. After #2 closed and #16 became ACTIVE, #17 still contained stale current-state wording (`#2 ACTIVE`, `#16 BLOCKED`) until explicitly repaired.

The no-op commit sequence does not change repository content, but it pollutes history and weakens trust in mutation discipline. The `__noop__` create/delete pair temporarily changed repository contents and required corrective cleanup.

## Root-cause analysis

### RC-1 — Missing pre-write semantic-diff gate
The write path checked neither “does the intended replacement differ from the fetched current content?” nor “is the returned content/blob SHA already the intended state?” before issuing another write.

Consequence: an already-successful update was treated as if another write might still be useful.

### RC-2 — Missing single-write stop condition
There was no hard rule that a successful mutation to a target ends that target's write phase until a fresh read proves another semantic change is required.

Consequence: repeated same-path `update_file` calls were possible even after success.

### RC-3 — Mutation action was not bound to an explicit intent tuple
Before the accidental `__noop__` creation, the operation was not guarded by an explicit tuple:

```text
(resource, target, action, expected semantic diff)
```

Consequence: a structural `create_file` action could be invoked even though the intended work was issue/protocol synchronization.

### RC-4 — Dependency fan-out was not treated as part of a state transition
Closing #2 and activating #16 updated the directly handled issue bodies, but there was no mandatory search for downstream current-state surfaces that referenced those states.

Consequence: #17 retained stale dependency wording even though its start condition remained correct.

## Contributing factors

- Sparse/commit-oriented tool responses were treated as a reason to continue writing instead of a reason to verify with a read.
- Repository content synchronization and dependency-status synchronization were not separated into an explicit target list before mutation.
- There was no prohibition on placeholder/no-op writes as a connectivity or tool-selection test.

## Corrective action

Canonical procedure added as:

```text
docs/protocols/repository_mutation.md
```

It introduces:
- read-before-write and semantic-diff gates;
- one successful write per target before mandatory re-read;
- explicit mutation-intent tuples;
- structural-action guardrails for create/delete/ref operations;
- dependency fan-out synchronization after issue state transitions;
- post-write verification and stale-text search;
- prohibition on placeholder/no-op commits.

`PROTOCOL_INDEX.md` routes all repository/issue/file mutation work through that procedure.

## Verification

Closure requires all of the following:

```text
#17 current-state text matches #2 CLOSED/PASS -> #16 ACTIVE -> #17 BLOCKED
__noop__ absent from repository root
repository-mutation protocol exists and is routed from PROTOCOL_INDEX.md
no second write is issued to a target after success unless a fresh read proves a new semantic diff
```

## History policy

Do not rewrite shared branch history merely to erase these commits. Preserve the incident as evidence and prevent recurrence prospectively.
