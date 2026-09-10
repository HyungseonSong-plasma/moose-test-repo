# Issue #187 automation-gate and mutation-routing incidents — 2026-09-10

## Scope

This record preserves two separate operational failures observed while advancing Issue #187 from the 32-import boundary toward zero legacy imports.

The scientific/import-cleanup work itself is distinct from these incidents. No Physics scientific PASS is inferred from either event.

---

## Incident A — Group A exact-count prerequisite caused rollback of valid progress

### Intended behavior

At the Group A boundary, deterministic CI had established:

```text
ISSUE143_EXTERNAL_LEGACY_IMPORTS = 32
```

Group A owns eight historical callers and should continue across intermediate successful reductions until the group reaches 24.

Correct state machine:

```text
start boundary: 32
valid in-progress range: 24 < census <= 32
completion boundary: 24
```

### Observed sequence

1. Group A migrated `experiments/Issue48_qpx_harness_generality/wp6_case_primitives_characterization.py`.
2. Commit `eeab29b175ea6828cb883cc7575548e46ccb5ef3` landed.
3. Ordinary CI run `34439282045` reported:

```text
ISSUE143_EXTERNAL_LEGACY_IMPORTS = 31
ISSUE143_ZERO_LEGACY = FAIL
```

The reduction from 32 to 31 was expected progress. The dependency-direction, cycle, experiment-gateway, plasma-semantic, performance/campaign, numerical-method, MOOSE-boundary guards and public immutable Physics runtime smoke remained PASS.

4. Immediately afterward, commit `9ddf9c3f906b8abf3450f005df4472aee3aeae2c` with message `revert(#187): restore Group A prerequisite state` restored the previous tree.
5. CI run `34439372621` then reconfirmed:

```text
ISSUE143_EXTERNAL_LEGACY_IMPORTS = 32
```

### Failure location

The failure was in the **automation prerequisite/state-transition gate**, not in the migrated source file or the architecture/runtime guards.

The task definition treated `census == 32` as a continuing prerequisite instead of only an entry boundary. Therefore a legitimate first-step reduction to 31 made the next automation iteration appear to violate its prerequisite, and the work was rolled back.

Primary classification:

```text
GATE_DEFECT
```

### Corrective action

The automation gate is replaced by a range-based continuation contract:

```text
Group A: 24 < census <= 32, complete at 24
Group B: 14 < census <= 24, complete at 14
Group C:  0 < census <= 14, complete at 0
```

A valid monotonic reduction inside the owning group's range must never be reverted solely because the census no longer equals the group's initial boundary.

---

## Incident B — wrong-action `__noop__` file mutation during Issue #187 status synchronization

### Intended action

```text
resource: issue
exact target: #187
intended mutator: GitHub.update_issue
purpose: synchronize the canonical Issue #187 state and record the Group A gate defect
```

### Actual wrong action

A file mutator was invoked instead with an explicitly forbidden placeholder target:

```text
mutator: GitHub.update_file
path: __noop__
content: empty
commit message: noop
commit: c5ee27c64def231a3724c6bc5d97ee6a1db00597
```

This violated the existing repository mutation controls, including the placeholder prohibition and the issue-vs-file recipient lock in RM-06D/RM-06F/RM-06H, and triggered RM-09/RM-09A.

Primary classification:

```text
KNOWN_AND_GATE_BYPASSED
```

### Live repair

The accidental target was immediately read back as:

```text
path: __noop__
blob: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
```

It was then removed with the exact structural delete operation:

```text
repair commit: 98c9368de2c8353e71570ebc08066ef630c8222b
post-repair verification: __noop__ -> 404 / absent
```

The repaired tree is `72781bb2080334eb6c4f2a60d7fb359a5c94b66f`, the same tree as the pre-incident Group A boundary state. No history rewrite was attempted.

### Failure location

The business intent and target identity were correct in analysis, but the **final mutator recipient selection** was wrong: an issue update intent was routed to a repository file mutator.

This is not a missing semantic rule. The relevant controls already existed and were active in the loaded mutation protocol; the failure was a final call-boundary enforcement bypass.

### Corrective action

Do not add a duplicate semantic mutation rule. Treat this as `STRENGTHEN_TRIGGER_OR_ROUTING`:

```text
issue business intent
-> exact issue mutator must be the next callable
-> any file mutator recipient is a hard stop
-> any placeholder target such as __noop__/noop/probe is a hard stop
-> after wrong-action mutation, RM-09A permits only repair + incident/governance recording in the same response
```

The originally intended general #187 business-state synchronization is not resumed inside the same wrong-action session.

## Current repository state after repair

```text
main = 98c9368de2c8353e71570ebc08066ef630c8222b
current tree = 72781bb2080334eb6c4f2a60d7fb359a5c94b66f
ISSUE143_EXTERNAL_LEGACY_IMPORTS = 32   # latest deterministic CI at this tree
Group A net landed progress = 0/8
Group B = not started
Group C = not started
```

The next legitimate business mutation must start from a fresh mutation context and fresh-read current repository/issue state.
