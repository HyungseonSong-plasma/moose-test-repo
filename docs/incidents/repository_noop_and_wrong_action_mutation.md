# Incident: Repository no-op and wrong-action mutations

**Incident ID:** `INC-REPO-MUTATION-001`  
**Status:** CLOSED / PROCESS FIXED — recurrence hardened  
**Associated work:** Issue #25 `Repository mutation safety + stale-state synchronization protocol`  
**Failure class:** assistant-side repository/governance mutation; no QPX physics impact

## Symptom

Two related repository-mutation defects were originally observed:

1. A README synchronization operation issued multiple `update_file` calls after the first successful semantic update. The later calls wrote identical content/blob state and created no-op commits.
2. During the cleanup/retrospective, a wrong mutator was invoked and created a placeholder root file `__noop__`; it was immediately removed in the next commit.
3. After #2 closed and #16 became ACTIVE, #17 still contained stale current-state wording (`#2 ACTIVE`, `#16 BLOCKED`) until explicitly repaired.

The no-op commit sequence does not change repository content, but it pollutes history and weakens trust in mutation discipline. The `__noop__` create/delete pair temporarily changed repository contents and required corrective cleanup.

## Recurrence after first process fix

A recurrence occurred immediately after `docs/protocols/repository_mutation.md` had been introduced. While resuming #16, the intended repository mutation was an **issue-body update to #16**, but an `update_file` call was accidentally issued against `README.md` with content identical to the fetched README state.

Observed result:

```text
commit: 2be5f419cef50f6190411110df43532ffc7d50c4
returned content SHA: c650f61a19c27a7208adfd9bba78255cca183a4a
pre-write README content SHA: c650f61a19c27a7208adfd9bba78255cca183a4a
```

This was another no-op history-polluting commit. No live repository content changed.

The recurrence demonstrates that a written intent tuple alone was insufficient: the guard must bind the intent to the **actual selected mutator recipient and target immediately before invocation**.

## Root-cause analysis

### RC-1 — Missing pre-write semantic-diff gate
The original write path checked neither “does the intended replacement differ from the fetched current content?” nor “is the returned content/blob SHA already the intended state?” before issuing another write.

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

### RC-5 — Intent was not frozen to the concrete tool recipient
The first protocol version required tool/action matching conceptually, but did not force the mutation intent to be converted into one allowed mutator and exact target before arguments were composed.

Consequence: during #16 resume, a nearby/previously loaded file mutator could still be selected even though the intended resource was an issue.

## Contributing factors

- Sparse/commit-oriented tool responses were treated as a reason to continue writing instead of a reason to verify with a read.
- Repository content synchronization and dependency-status synchronization were not separated into an explicit target list before mutation.
- There was no prohibition on placeholder/no-op writes as a connectivity or tool-selection test.
- Tool availability/context made it possible to select a previously loaded mutator unless the resource-target binding was rechecked at the call boundary.

## Corrective action

Canonical procedure:

```text
docs/protocols/repository_mutation.md
```

The first process fix introduced:
- read-before-write and semantic-diff gates;
- one successful write per target before mandatory re-read;
- explicit mutation-intent tuples;
- structural-action guardrails for create/delete/ref operations;
- dependency fan-out synchronization after issue state transitions;
- post-write verification and stale-text search;
- prohibition on placeholder/no-op commits.

After the recurrence, the protocol was strengthened with:

```text
RM-06A Mutator recipient freeze
RM-06B File byte-state guard
```

RM-06A requires the intended resource, exact target, and one allowed mutator to be frozen before mutation arguments are composed, and rechecked against the selected function immediately before invocation. RM-06B explicitly forbids `update_file` when intended and fetched bytes are identical.

`PROTOCOL_INDEX.md` continues to route all repository/issue/file mutation work through that single canonical procedure.

## Verification

The process fix is considered active when all of the following hold:

```text
#17 current-state text matches #2 CLOSED/PASS -> #16 ACTIVE -> #17 BLOCKED
__noop__ absent from repository root
repository-mutation protocol exists and is routed from PROTOCOL_INDEX.md
no second write is issued to a target after success unless a fresh read proves a new semantic diff
issue intent cannot invoke a file mutator without failing RM-06A
update_file cannot run on byte-identical fetched/intended content under RM-06B
```

## History policy

Do not rewrite shared branch history merely to erase these commits. Preserve the incident and recurrence as evidence and prevent recurrence prospectively.
