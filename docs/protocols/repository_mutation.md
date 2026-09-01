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

## RM-05A — Post-write verification read-only lock

Once a successful write enters post-write verification, the workflow is in **VERIFY mode** and must be action-locked to read-only tools.

Permitted actions in VERIFY mode:

```text
fetch/read/get/open/search of the just-written canonical target
```

Forbidden actions in VERIFY mode:

```text
update_*
create_*
delete_*
move/ref mutation
comment/reaction mutation
any other mutator, even against the correct resource and correct target
```

Do not reuse the prior write payload, intended replacement content, blob SHA, or a nearby mutator call merely to “verify” propagation. Verification proves state by reading it.

A new mutation to the same target may begin only after:

```text
1. VERIFY mode completed with a fresh canonical read;
2. a new semantic difference is explicitly identified;
3. a new RM-01 intent tuple and RM-03 semantic-diff gate are constructed.
```

If a mutator is invoked during VERIFY mode, treat it as a wrong-action mutation even when the bytes remain identical and the resource/target are correct. Apply RM-09/RM-09A.

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

## RM-06C — Create-action exact-target attestation

Every `create_*` mutation requires an exact pre-create target identity already present in the RM-08 plan before the mutator is selected.

Use the resource's real pre-create identity:

```text
create issue   -> exact repository + intended title/purpose
create file    -> exact repository path
create branch  -> exact repository + branch name + source ref
create comment -> exact repository + issue/PR number + intended comment purpose
```

Immediately before invocation verify:

```text
selected create mutator resource class == planned resource class
selected target identity == planned target identity
no placeholder, probe, stand-in, or invented surrogate target is present
```

For server-assigned resources such as issues, the absence of the future numeric ID does not permit a substitute target. The repository plus intended title/purpose is the target identity until creation returns the canonical ID.

If the required create mutator is not currently loaded, discover/load that exact mutator and then call it. Never substitute another `create_*` action merely to test availability or preserve flow.

## RM-06D — Resource-class payload-shape lock

The frozen `INTENT_RESOURCE` must constrain not only the mutator name but also the **argument schema** allowed to reach a write call.

Before invocation, inspect the composed payload itself:

```text
INTENT_RESOURCE=issue
  -> payload must contain issue identity fields
  -> any repository file path/content/blob-SHA mutation fields are a HARD STOP

INTENT_RESOURCE=file
  -> payload must contain the exact planned repository path
  -> any issue-number/title/body mutation fields are a HARD STOP
```

Equivalent checks apply to branch/ref and comment resources. A payload shape belonging to another resource class proves mutator-routing failure even if the prose intent is correct.

Required pre-call decision:

```text
selected mutator == ALLOWED_MUTATOR
AND
payload resource class == INTENT_RESOURCE
AND
payload target == INTENT_TARGET
```

If any term is false, do not invoke any write tool. Do not replace the payload with a placeholder target, empty file, dummy path, or probe action.

This check is mandatory after prior wrong-action incidents because a correct written intent alone has not prevented file mutators from being selected during issue updates.

## RM-06E — Mutation-enabled phase latch

Repository mutators are forbidden unless the **current workflow step itself is explicitly a planned mutation step**. Tool availability, a previously approved work package, or a valid earlier mutation intent does not keep mutation permission open across unrelated work.

Maintain an internal phase latch:

```text
MUTATION_ALLOWED = false   # default
```

Set it to `true` only immediately before one predeclared RM-08 mutation target after RM-01/RM-03/RM-06 checks have passed. Reset it to `false` immediately after the mutator returns, before verification or any local/sandbox analysis begins.

The following phases must always have `MUTATION_ALLOWED=false`:

```text
local staging
code generation in sandbox/container
syntax/self-test execution
read/search/discovery
post-write verification
analysis/planning
commentary/status updates
tool-schema discovery
```

Hard pre-call gate:

```text
if MUTATION_ALLOWED != true:
    every create_*/update_*/delete_*/ref/comment mutator is FORBIDDEN
```

A valid-looking target does not override this gate. An accidental mutator call while `MUTATION_ALLOWED=false` is a wrong-action mutation and must trip RM-09A immediately.

## RM-06F — Adjacent one-shot mutation envelope

Immediately before every repository mutator, freeze a one-shot call envelope **after** the fresh read, semantic diff, resource-class check, and RM-08 target selection are complete.

Required envelope:

```text
NEXT_MUTATION_RESOURCE = exact resource class
NEXT_MUTATION_TARGET = exact issue number/path/ref
NEXT_MUTATION_ACTION = exact action
NEXT_MUTATION_MUTATOR = exact mutator function
NEXT_MUTATION_TARGET_KEY = issue_number | path | branch/ref key | comment id
NEXT_MUTATION_EXPECTED_DIFF = exact semantic change
NEXT_MUTATION_PREWRITE_IDENTITY = issue state/body identity or file blob/content SHA
```

The envelope authorizes **exactly one immediate next tool call**. The next call must be the frozen mutator against the frozen target.

Any intervening action invalidates the envelope and resets mutation permission:

```text
commentary/status update
analysis/planning
read/search/fetch
local/sandbox execution
tool discovery/schema lookup
any different tool call
```

After invalidation, return to `MUTATION_ALLOWED=false` and rebuild the envelope from a fresh canonical read before any mutation.

Hard call-boundary rule:

```text
selected mutator == NEXT_MUTATION_MUTATOR
AND payload target key == NEXT_MUTATION_TARGET_KEY
AND payload target == NEXT_MUTATION_TARGET
AND target appears in the pending RM-08 plan
```

If any term is false, the call is forbidden.

For `update_file`, the envelope must also carry the fresh pre-write blob/content identity and prove:

```text
intended replacement bytes != fresh-read bytes
```

Commit messages or payloads whose purpose is `noop`, `probe`, `connectivity test`, `ensure`, `make sure`, or equivalent are prohibited. An identical-content `update_file` is forbidden even if the target path is valid.

For issue mutations, any file-mutator recipient or payload containing file `path`/blob-SHA/content replacement fields invalidates the envelope. For file mutations, issue-number/title/body/state payloads invalidate the envelope.

The envelope is consumed when its one mutator returns, whether the mutation succeeds or fails. Verification then occurs under RM-05A with `MUTATION_ALLOWED=false`.

## RM-06G — Cross-resource mutation isolation after recurrence

After repeated wrong-action incidents, this repository uses a stricter response-level interlock:

```text
one assistant response / live mutation phase = one repository resource class
```

If a response begins an **issue** mutation phase, only issue mutators are allowed for business work in that response. File implementation must wait for a later fresh response after the issue mutation is read-back verified.

If a response begins a **file** mutation phase, only file mutators are allowed for business work in that response. Issue-body/status synchronization must occur in a separate fresh response.

Equivalent isolation applies to branch/ref and comment mutation phases. Do not mix resource classes merely because all targets were listed in one RM-08 plan.

The only exception is RM-09A incident handling, where minimal repair plus incident/protocol governance mutations are explicitly permitted.

This rule is specifically intended to prevent a planned issue transition from being accidentally routed to a file mutator, or vice versa. If the intended work requires both governance and implementation:

```text
response A: issue-only mutation + read-only verification
response B: fresh protocol read + file-only implementation mutations + verification
response C: optional issue-only evidence/status synchronization
```

A fresh response boundary is therefore part of the mutation safety contract after recurrence, not optional workflow polish.

## RM-06H — Exact mutator availability is a hard precondition

After a fourth wrong-action recurrence, a planned repository mutation may proceed only when the exact mutator frozen in the one-shot envelope is the actual callable selected for the immediate next tool call.

Required gate:

```text
NEXT_MUTATION_MUTATOR is available
AND selected callable == NEXT_MUTATION_MUTATOR
AND selected callable's resource class == NEXT_MUTATION_RESOURCE
AND selected payload target == NEXT_MUTATION_TARGET
```

If the exact mutator is unavailable, cannot be addressed unambiguously, or does not accept the planned target identity, the only valid action is:

```text
STOP / NO REPOSITORY MUTATION
```

Never substitute a different mutator, different resource class, surrogate target, dummy file, placeholder issue, probe payload, or connectivity-test action. Tool unavailability is a reason to defer the mutation, not to approximate it.

For create operations, the server-assigned future identifier does not relax this rule. The pre-create target identity from RM-06C remains authoritative until the exact create mutator returns the canonical identifier.

## RM-06I — Bulk snapshot mutator-family lock

When the intended semantic change is a validated directory/tree replacement, declare the upload mode before any repository write:

```text
UPLOAD_MODE = git_tree_snapshot
SNAPSHOT_TARGET = exact directory/tree path
SNAPSHOT_MANIFEST = exact validated local file set
```

In that file-object phase, the business mutator family is locked to Git object construction:

```text
PERMITTED:
  create_tree for the validated snapshot
  create_commit for the immutable snapshot commit

FORBIDDEN:
  create_file
  update_file
  delete_file
  any contents-API staging file
  any placeholder/sentinel/probe path
  branch/ref movement in the same response
```

Every tree entry must come from `SNAPSHOT_MANIFEST`; no extra path may be invented at invocation time. If the selected next mutator is a contents-API file action, or if its path is not in the validated manifest, this is a hard stop before the call.

After the immutable snapshot commit is read-back verified, move the branch/ref only from a fresh branch/ref mutation response under RM-06G. Do not use a temporary file to prove that the branch or connector is writable.

## RM-06J — Structural-action opcode lock

For high-impact structural mutations, freeze the exact action family independently from resource class and target. The selected callable name must literally match the frozen structural opcode.

Canonical mapping:

```text
delete existing file -> delete_file(path=<exact path>, sha=<fresh blob SHA>)
create new file       -> create_file(path=<exact path>)
move branch/ref       -> update_ref(branch_name=<exact branch>, sha=<intended commit>)
```

Hard rule:

```text
NEXT_MUTATION_ACTION == delete existing file
  -> selected callable MUST be delete_file
  -> payload MUST contain exact file path + fresh blob SHA
  -> update_ref/create_file/update_file/create_tree/create_commit are FORBIDDEN

NEXT_MUTATION_ACTION == move branch/ref
  -> selected callable MUST be update_ref
  -> file-content mutators are FORBIDDEN
```

A branch name being correct, a branch already pointing at the supplied SHA, or a wrong structural call producing no semantic change does not make the action acceptable. Any mismatch between the frozen structural action and the selected callable trips RM-09A before the originally intended business mutation can continue.

## RM-07 — State-transition fan-out synchronization

When an issue changes lifecycle/dependency state (for example ACTIVE -> CLOSED/PASS, BLOCKED -> ACTIVE, or one blocker is replaced by a successor), treat downstream current-state synchronization as part of the same governance operation.

**Discover the fan-out before the first write.** A state transition must not begin by mutating the canonical issue and only afterward discovering downstream current-state surfaces one at a time.

Procedure:

```text
1. fetch the canonical issue that is expected to change
2. search open/current-state surfaces for the old issue number, status phrase, blocker edge, and directly dependent work items
3. distinguish historical evidence/comments from current-state text
4. place every known stale current-state target into the RM-08 pre-mutation plan
5. perform the canonical state change
6. update only the predeclared stale current-state surfaces sequentially
7. run a final stale-phrase/dependency search to catch genuinely missed surfaces
8. do not rewrite historical issue comments/evidence
9. verify the resulting dependency chain is internally consistent
```

Typical current-state surfaces:
- dependent open issue bodies;
- README/current-development summary when it intentionally mirrors active state;
- milestone/current-work summary documents.

Historical comments and incident records must retain historical wording.

If the final search reveals a target that could reasonably have been discovered by the pre-write search, treat that as a fan-out planning miss and improve the discovery query rather than normalizing repeated post-write cleanup.

## RM-08 — Pre-mutation target plan

For a multi-target synchronization, list the exact targets before the first write and execute sequentially.

Example:

```text
Target A: issue #2 state -> CLOSED/PASS
Target B: issue #16 blocker -> removed / ACTIVE
Target C: issue #17 upstream text -> synchronized
Target D: README current sequence -> synchronized
```

For lifecycle/dependency mutations, the target plan must be built from the RM-07 **pre-write fan-out search**, not only from conversation memory or direct dependents already known to the operator.

For create operations, the plan must state the exact pre-create target identity defined by RM-06C before the first create call.

Do not discover new mutation targets by repeatedly writing. Discovery is read/search work.

## RM-09 — Commit/no-op hygiene

The following are operating errors:
- repeated identical-content writes;
- placeholder commits/files;
- create-then-delete probes;
- repeated update attempts after a success without fresh-read evidence;
- mutator invocation during RM-05A VERIFY mode;
- mutator invocation while RM-06E `MUTATION_ALLOWED=false`;
- mutator invocation that does not match the active RM-06F one-shot envelope;
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

## RM-09A — Session circuit breaker after wrong-action mutation

If a repository mutation acts on the wrong resource class, wrong target, or wrong action for the current phase and reaches live repository state/history, trip a session-level circuit breaker.

For the remainder of the same assistant response/session:

```text
PERMITTED:
  read/verify repository state
  minimal repair of the accidental live target
  incident-record update
  canonical mutation-safety rule update required by RM-09

FORBIDDEN:
  the originally intended business mutation
  new issue/file/branch creation unrelated to repair
  dependency synchronization
  retries intended to prove the new guard works
```

After repair and governance recording, verify the accidental target is absent, restored, or byte-identical when the failure was a no-op, then end the repository write phase. Resume intended/business mutations only from a fresh mutation context that reloads the canonical mutation protocol and reconstructs the RM-08 plan from current state.

A repeated wrong-action mutation after a guard update is evidence that the current mutation context is unsafe; it is not permission to test another mutator.

## RM-10 — Final mutation closure check

Before declaring repository synchronization complete, verify:

```text
all intended targets have the expected semantic state
no unintended created target remains
no known stale current-state phrase remains in direct dependents or other open current-state surfaces discovered by RM-07
no target received an unjustified second write
all protocol/index references point to one canonical owner
```

For dependency changes, perform a final search using the old status/dependency phrase and relevant old issue number. A hit in historical evidence is acceptable; a hit in a current open issue body is not.

## RM-11 — Incident promotion trigger

A new repository-mutation failure class is material when it can pollute history, change live repository state, or leave canonical current state inconsistent. Record it under `docs/incidents/` and promote the reusable prevention here rather than creating overlapping mutation guides.

Current originating incident:

```text
docs/incidents/repository_noop_and_wrong_action_mutation.md
```

## RM-12 — Resource-class schema-surface isolation

Once a response declares a live mutation resource class, tool-schema discovery must preserve that same resource-class boundary **before** any business mutator is called.

Canonical rule:

```text
ACTIVE_MUTATION_RESOURCE = file
  -> discover/load file mutators only
  -> issue/comment/branch mutator schema loading is a HARD STOP for business mutation

ACTIVE_MUTATION_RESOURCE = issue
  -> discover/load issue mutators only
  -> file/comment/branch mutator schema loading is a HARD STOP for business mutation
```

Read-only tools from other resource classes may still be used when required for discovery or verification, but mutator-schema discovery is resource-class scoped.

If a mutator schema from the wrong resource class is loaded after the mutation phase has been frozen, treat the current tool surface as contaminated:

```text
MUTATION_ALLOWED = false
business mutation for this response = FORBIDDEN
resume only in a fresh response with the intended resource class reloaded
```

Do not test whether the wrong-resource mutator is harmless. Do not invoke it with a placeholder target. Do not rely on the later RM-06D payload check to recover safety. The purpose of this rule is to remove unrelated mutators from the callable surface before target/action binding occurs.

Originating recurrence:

```text
docs/incidents/issue60_wrong_action_placeholder_issue65_2026-09-01.md
```
