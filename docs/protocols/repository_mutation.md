# Repository Mutation Safety Protocol

**Status:** canonical procedure  
**Scope:** GitHub issue/file/branch/ref/Git-object mutations and repository state synchronization  
**Purpose:** preserve canonical repository correctness without allowing process guards to block otherwise safe forward progress.

This procedure separates **real repository-safety failures** from **soft control anomalies**. A mutation workflow stops only when canonical repository state is at risk, the intended change cannot be proven safe, or an explicitly gated validation run is active. Soft control anomalies are diagnosed and recorded, but they do not automatically terminate valid work.

## RM-01 — Intent and target binding

Before a repository mutation, identify:

```text
resource = issue | file | branch/ref | comment | git-object | other
exact target = issue number, repository path, ref, or intended Git object purpose
action = create | update | delete | close/open | add/remove | move ref | construct snapshot
expected semantic diff = what must become different
expected unchanged scope = what must remain unchanged
```

The mutation must target the identified resource and implement the identified action. Do not substitute a different resource or surrogate target.

## RM-02 — Fresh read before write

For an existing canonical target, fetch its current state immediately before mutation.

For files, retain the current blob SHA and the content needed to construct the replacement. For issues, retain the fields being changed. For branch/ref movement, retain the current head SHA. For a Git snapshot, retain the base tree/parent commit identity.

Conversation memory is not a substitute for a fresh canonical read when the target is available from GitHub.

## RM-03 — Semantic-diff gate

Do not intentionally write an unchanged canonical state.

```text
intended semantic state == current semantic state
    -> NO_MUTATION_NEEDED
```

Formatting-only changes are allowed only when formatting itself is the intended change.

## RM-04 — Exact mutator binding

Immediately before mutation, verify:

```text
selected mutator implements intended action
payload target == exact target
payload resource class == intended resource class
```

Examples:

```text
update issue       -> update_issue
update file        -> update_file with fresh blob SHA
create file        -> create_file at exact intended path
delete file        -> delete_file with fresh blob SHA
move branch/ref    -> update_ref with intended commit SHA
construct snapshot -> Git-object operations tied to the declared snapshot
```

A wrong resource, wrong target, or wrong structural action is not made acceptable merely because the resulting state happens to be unchanged.

## RM-05 — Post-write verification

After every successful canonical mutation, verify the result read-only before relying on it.

Verify at minimum:

```text
target identity
expected semantic state
unexpected collateral changes absent
resulting SHA/state when available
```

Do not repeat the same write merely to confirm propagation.

A second mutation to the same target is allowed when a fresh read proves a distinct remaining semantic difference.

## RM-06 — HARD STOP conditions

A **HARD STOP** is reserved for conditions that threaten or obscure canonical repository correctness.

Stop repository mutation and diagnose before continuing when any of the following is true:

1. A mutator changed the **wrong canonical resource or wrong canonical target**.
2. A structural operation performed the **wrong action** and changed live canonical state or history.
3. A branch/ref movement is non-fast-forward unless history rewriting was explicitly authorized.
4. The current canonical state cannot be determined reliably enough to construct the intended mutation.
5. The intended replacement cannot be distinguished from a no-op where the mutation would create unwanted history.
6. Post-write verification shows an unexpected canonical state, collateral change, or inconsistent dependency state.
7. An exact-head CI/science validation lock is active and repository policy requires that run to complete before further mutation.
8. A destructive operation lacks the exact target identity or fresh pre-write identity required to execute safely.
9. Repeated tool-routing errors make it impossible to establish which canonical target would be mutated next.

When a HARD STOP occurs:

```text
stop further business mutation
verify canonical state
repair only actual unintended canonical state when necessary
record the incident when material
resume once the target/action/state is again provably safe
```

A fresh assistant-response boundary is **not inherently required**. Safety is established by fresh state, exact target/action binding, and verification.

## RM-07 — SOFT CONTROL conditions

A **SOFT CONTROL** anomaly is a warning, diagnostic, or harness problem that does not by itself threaten canonical repository state.

The following are soft controls unless additional evidence shows a real repository-safety failure:

1. Tool-schema discovery exposes unrelated mutators.
2. A checker detects a forbidden token that appears only in a negative test, comment, guard, or diagnostic string.
3. A validator/checker produces a false positive before production build/runtime execution.
4. A Git blob/tree object is created but remains unattached to every canonical commit/ref and no canonical state changes.
5. A read-only verification reveals that an attempted operation had no semantic effect.
6. A tool is unavailable or inconvenient but another **exactly equivalent, target-correct** safe path exists.
7. A protocol assertion fails because of process metadata while the exact target, action, and canonical state remain independently verifiable.

For a soft control:

```text
classify the anomaly
verify that canonical state is safe
correct the guard/checker/tool route when needed
continue the intended work when target/action binding remains unambiguous
```

Do **not** convert a soft control into a repository-wide or response-wide circuit breaker merely because it occurred.

## RM-08 — Validator failure classification

Validation failures must be classified by the layer that actually failed.

```text
P0 checker/self-test failure
    -> checker/harness/construction failure unless physics executed

P1 static failure
    -> implementation/static-contract failure

P2 check-input/preflight failure
    -> construction/configuration/interface failure unless evidence proves physics semantics

P3 runtime discriminator failure
    -> bounded runtime/physics failure only for the semantics actually exercised
```

A workflow-level `failure` conclusion must not automatically be reported as a physics failure.

Forbidden-token checks must inspect the **production-generating surface**, not blindly reject a token because the checker itself mentions that token in a negative-control guard.

## RM-09 — Multi-target and multi-resource progress

Multiple repository targets or resource classes may be handled in one response when all of the following hold:

```text
each intended target is known before its write
each write uses the correct resource/action/target
writes are sequential where ordering matters
each completed write is verified before a dependent write proceeds
no exact-head CI/science mutation lock is active
```

There is no general requirement to split file, ref, and issue synchronization across separate assistant responses.

Use separate phases only when the operations are causally independent enough that separation improves safety or when an active CI/science lock requires it.

## RM-10 — Git-object and snapshot operations

Git-object construction is allowed when it directly serves an identified immutable snapshot/commit operation.

Before constructing a snapshot, identify:

```text
base tree / parent commit
intended changed paths
intended resulting commit purpose
```

`create_blob`, `create_tree`, and `create_commit` may be used as parts of that construction when each generated object is attributable to the intended snapshot.

Unexpected unattached Git objects are a **soft incident** when all of the following are verified:

```text
no branch/ref moved
no commit reachable from a canonical ref contains the object
no canonical file/tree state changed
```

Do not rewrite shared history merely to hide unreachable objects. Record material recurrence and improve routing prospectively.

## RM-11 — Branch/ref safety

Branch/ref movement requires:

```text
fresh current ref
intended destination commit
ancestry/compare check when practical
force = false by default
```

If the destination is not a fast-forward, stop unless the user explicitly authorizes history rewriting.

After ref movement, read the ref back and verify the exact head SHA.

## RM-12 — CI/science mutation lock

When a canonical mutation triggers required exact-head CI or governed science validation, repository mutation is locked until the required run set completes.

During the lock:

```text
read-only inspection, logs, artifacts, and diagnosis are allowed
repository writes are not allowed
```

After completion:

- success permits the next planned mutation/acceptance step;
- failure is classified by the actual failing validation layer under RM-08;
- checker/harness false positives may be repaired without labeling the underlying physics as failed.

## RM-13 — Dependency/state synchronization

When changing lifecycle or dependency state, discover direct current-state fan-out before or during the synchronization and update stale canonical surfaces sequentially.

Historical evidence and incident records must not be rewritten merely because current state changed.

A missed downstream surface is a planning defect to repair; it is not automatically a session-wide stop unless the repository is left materially inconsistent and the correct state cannot be established.

## RM-14 — Placeholder and probe prohibition

Do not create canonical files, commits, refs, issues, or comments solely to test whether a mutator works.

Surrogate targets and connectivity-test mutations are forbidden. Tool capability is established through schema/discovery/read operations, not live repository pollution.

An accidentally created **unreachable Git object** is handled under RM-10; an accidentally created reachable canonical resource is handled as a HARD STOP under RM-06.

## RM-15 — Incident severity

Classify repository-operation incidents by effect:

```text
SEV-A  canonical wrong-state mutation / destructive or history-affecting error
       -> HARD STOP

SEV-B  canonical no-op history pollution or recoverable wrong action
       -> stop that action, verify/repair, then continue when safe

SEV-C  checker/schema/tool-routing anomaly with no canonical state change
       -> SOFT CONTROL; diagnose and continue

SEV-D  informational warning with no mutation effect
       -> record only if useful
```

Escalation depends on actual effect and uncertainty, not merely on the presence of a mutator name in the tool surface.

## RM-16 — Completion criteria

Repository synchronization is complete when:

```text
all intended canonical targets have the expected semantic state
no unintended reachable resource remains
required branch/ref destinations are verified
required exact-head CI/science gates have completed successfully or are explicitly classified
current dependency state is internally consistent
no unjustified repeated write was performed
```

## Operating principle

The safety objective is **canonical correctness with forward progress**.

Use hard stops for real state risk. Use soft controls for false positives, checker defects, schema exposure, and other process anomalies that can be independently shown not to affect canonical state. A safety protocol that repeatedly blocks verified-safe work is itself a liveness defect and should be simplified rather than strengthened mechanically.
