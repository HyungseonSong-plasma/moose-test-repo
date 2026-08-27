# Repository Mutation Safety Protocol

**Status:** canonical procedure  
**Scope:** GitHub issue/file/branch/ref mutations and repository state synchronization  
**Purpose:** prevent no-op commits, wrong-action writes, repeated same-target writes, and stale current-state copies.

Use this procedure whenever the requested work mutates repository state. It complements `OPERATING_CORE.md`; it does not change meeting/approval semantics.

## RM-01 — Mutation intent tuple

Before every mutation, state internally and unambiguously:

```text
resource = issue | file | branch/ref | comment | other
exact target = issue number or repository path/ref
mutation action = create | update | delete | close/open | add/remove | move ref
expected semantic diff = what must become different
expected unchanged scope = what must not change
```

If any field is unresolved, do not mutate yet.

Structural actions (`create`, `delete`, branch/ref movement) require an exact target and a positive reason. Placeholder targets such as `__noop__`, fake files, or connectivity-test commits are prohibited.

## RM-02 — Read before write

For an existing target, fetch the current canonical state immediately before mutation.

For files record the current blob SHA and full content required to construct the replacement. For issues record the current body/state fields being changed.

Do not write from stale conversation memory when the target can be fetched.

## RM-03 — Semantic-diff gate

Construct the complete intended replacement, then compare it with the fetched current state.

```text
if intended semantic state == current semantic state:
    STOP -> NO_MUTATION_NEEDED
```

A no-op is a successful decision to avoid a write, not a reason to create a commit.

Formatting-only changes must be intentional and attributable; they are not a substitute for a semantic change.

## RM-04 — One successful write per target

After one successful mutation to a target, the write phase for that target is closed.

A second mutation to the same target is allowed only when:

1. a fresh post-write read is performed;
2. that read proves a new semantic difference remains; and
3. the second expected diff is explicitly identified.

Sparse tool output, uncertainty about propagation, or desire to “make sure” are not valid reasons for another write.

## RM-05 — Post-write verification

After every successful mutation, verify with a read or returned canonical snapshot before moving on.

For files verify:
- target path;
- expected content/state;
- resulting blob/content SHA when available.

For issues verify:
- issue number;
- state/state reason when changed;
- canonical body status/dependency text.

If a write returns success but the semantic state is unchanged unexpectedly, classify it as a no-op mutation incident and STOP. Do not repeat the same write.

## RM-06 — Tool/action binding guard

Immediately before invocation, match the selected mutator against the mutation intent tuple.

Examples:

```text
update existing issue body -> update_issue
create new issue -> create_issue
update existing file -> update_file using fetched blob SHA
create new canonical file -> create_file only after confirming path does not exist
delete file -> delete_file using freshly fetched blob SHA
```

If the tool action does not exactly implement the intended action, do not call it.

Create/delete/ref movement are treated as high-impact structural operations and must never be used as tool probes.

## RM-06A — Mutator recipient freeze

The intent tuple must be converted into a single allowed mutator **before mutation arguments are composed**.

Freeze internally:

```text
INTENT_RESOURCE = issue | file | branch/ref | comment | other
INTENT_TARGET   = exact issue number or path/ref
ALLOWED_MUTATOR = exact mutation function
```

Immediately before the call, verify all three again against the selected function and its target field. If the selected function operates on a different resource class or target, STOP before invocation.

Examples:

```text
INTENT_RESOURCE=issue, INTENT_TARGET=#16
  -> ALLOWED_MUTATOR=update_issue
  -> update_file/create_file/delete_file are forbidden in this write phase

INTENT_RESOURCE=file, INTENT_TARGET=README.md
  -> ALLOWED_MUTATOR=update_file
  -> issue mutators are forbidden in this write phase
```

Do not reuse a mutator recipient or payload shape from a previous repository operation merely because it is already loaded or nearby in context. A multi-target operation may switch mutators only after the previous target has been post-write verified and the next target appears explicitly in the RM-08 plan.

## RM-06B — File byte-state guard

For `update_file`, compare the complete intended replacement with the freshly fetched file content before invoking the mutator.

```text
intended bytes == fetched bytes -> STOP / NO_MUTATION_NEEDED
```

When a fetched content/blob SHA and a returned content/blob SHA are available, equality after an intended semantic change is an incident signature, not a reason to retry the write.

## RM-07 — State-transition fan-out synchronization

When an issue changes lifecycle/dependency state (for example ACTIVE -> CLOSED/PASS, BLOCKED -> ACTIVE), treat downstream current-state synchronization as part of the same governance operation.

Procedure:

```text
1. update the canonical issue that changed state
2. identify direct downstream/dependent open issues
3. search current-state surfaces for the old status phrase or dependency edge
4. update only stale current-state surfaces
5. do not rewrite historical issue comments/evidence
6. verify the resulting dependency chain is internally consistent
```

Typical current-state surfaces:
- dependent open issue bodies;
- README/current-development summary when it intentionally mirrors active state;
- milestone/current-work summary documents.

Historical comments and incident records must retain historical wording.

## RM-08 — Pre-mutation target plan

For a multi-target synchronization, list the exact targets before the first write and execute sequentially.

Example:

```text
Target A: issue #2 state -> CLOSED/PASS
Target B: issue #16 blocker -> removed / ACTIVE
Target C: issue #17 upstream text -> synchronized
Target D: README current sequence -> synchronized
```

Do not discover new mutation targets by repeatedly writing. Discovery is read/search work.

## RM-09 — Commit/no-op hygiene

The following are operating errors:
- repeated identical-content writes;
- placeholder commits/files;
- create-then-delete probes;
- repeated update attempts after a success without fresh-read evidence;
- unnecessary history rewrite used to conceal an assistant mutation error.

When such an error occurs:

```text
stop further mutation
repair any live accidental state minimally
record the incident/root cause
add or strengthen one canonical preventive rule
resume only after the new guard is clear
```

Shared-branch history is preserved by default; prevention is prospective unless the user explicitly authorizes history surgery.

## RM-10 — Final mutation closure check

Before declaring repository synchronization complete, verify:

```text
all intended targets have the expected semantic state
no unintended created target remains
no known stale current-state phrase remains in direct dependents
no target received an unjustified second write
all protocol/index references point to one canonical owner
```

For dependency changes, perform a final search using the old status/dependency phrase. A hit in historical evidence is acceptable; a hit in a current open issue body is not.

## RM-11 — Incident promotion trigger

A new repository-mutation failure class is material when it can pollute history, change live repository state, or leave canonical current state inconsistent. Record it under `docs/incidents/` and promote the reusable prevention here rather than creating overlapping mutation guides.

Current originating incident:

```text
docs/incidents/repository_noop_and_wrong_action_mutation.md
```
