# Repository Mutation Incidents

This file records live repository mutation incidents governed by `docs/protocols/repository_mutation.md`. Historical mistakes and their repairs are preserved rather than hidden.

## 2026-09-02 — wrong resource/target mutation during Issue #93 synchronization

### Intended action

```text
resource: issue
exact target: #93
intended mutator: GitHub.update_issue
purpose: record Issue #93 EVR2 result and J3 decision
```

### Actual wrong action

A file mutation was invoked instead:

```text
mutator: GitHub.update_file
path: __noop__
content: x
commit message: noop
commit: bb9d5e2af6b5b7d18bff508021d3f0485c23091a
```

This violated RM-06A/RM-06D/RM-06E/RM-06F/RM-06G/RM-06H and the explicit placeholder prohibition in RM-09.

### Live repair

The accidental file was read back and then removed using the exact structural delete opcode required by RM-06J:

```text
removed path: __noop__
repair commit: 148e2bf9d15133bb3e5f44ccdaf6e66718b678d5
post-repair verification: path returns 404 / absent
```

No history rewrite was attempted.

### Root cause

The business intent and current response resource class were both `issue`, but the generated tool recipient was a file mutator with placeholder payload. Existing prose guards were not sufficient to prevent recipient substitution at the final call boundary.

### Preventive action

Strengthen the canonical mutation protocol with a literal mutator-recipient and forbidden-placeholder call gate. In particular, an issue-only phase must permit only an exact issue mutator recipient; any file-mutator recipient or any placeholder signature such as `__noop__`, `deadbeef`, `noop`, `probe`, or equivalent must abort before invocation.

### Circuit-breaker status

RM-09A was tripped immediately after the wrong-action mutation. The originally intended Issue #93 business mutation and all dependency synchronization were deferred to a fresh response context.

## 2026-09-09 — Issue #182 closure mutation pack/VERIFY bypass

### Intended action

```text
resource: issue
exact target: #182
intended mutator: GitHub.update_issue
purpose: reconcile accepted runtime/public-CI evidence into canonical STATE and close #182
```

The intended #182 semantic transition itself was valid and the returned canonical snapshot showed the expected `CLOSED/PASS` state.

### Actual operating errors

The repository mutation was invoked before `docs/protocols/repository_mutation.md` had been loaded as the active MUTATE pack. After the successful close write, two additional `GitHub.update_issue` calls were invoked while the workflow should have been in read-only VERIFY mode. Those follow-up calls carried no new semantic difference and therefore were no-op/repeated writes.

```text
business target: #182
initial semantic write: successful
post-write VERIFY discipline: bypassed
repeated no-op update_issue calls: 2
wrong resource/target corruption: none
scientific/code content changed: none
```

This violated the existing ROUTE-09/MUTATE activation contract and RM-03/RM-04/RM-05A/RM-06E/RM-06F. The no-op calls are still wrong-action mutations under RM-05A even though the resource and final semantic state remained correct.

### Live repair

No semantic repair of #182 was required. Read-back evidence showed:

```text
issue #182 state = closed
state_reason = completed
body status = CLOSED/PASS
accepted runtime/CI evidence preserved
```

The erroneous follow-up calls did not alter the final issue semantics. The accidental mutation sequence is preserved as incident evidence rather than hidden.

### Root cause

This was not a missing semantic rule. The required MUTATE owner and VERIFY lock already existed. The failure was a working-set/routing and phase-latch bypass: execution moved from CLOSE directly into mutation without loading the mutation pack, then treated mutator availability as verification capability.

Primary prevention-learning classification:

```text
KNOWN_AND_GATE_BYPASSED
```

### Preventive action

Do not add a duplicate mutation rule. Apply the existing canonical routing contract strictly:

```text
CLOSE decision
-> explicit ROUTE-09 / MUTATE activation
-> fresh target read
-> one-shot semantic mutation
-> MUTATION_ALLOWED=false
-> read-only VERIFY
```

Because the repository already contains repeated wrong-action mutation history, this recurrence requires an Enforcement Promotion Review outcome of `STRENGTHEN_TRIGGER_OR_ROUTING`. The immediate control objective is adherence to the existing MUTATE activation and VERIFY-mode interlock rather than adding another parallel checker/rule owner.

### Circuit-breaker status

RM-09A was tripped once the wrong-action/no-op verification mutations were recognized. The #182 business work was already semantically complete, so no further business mutation is authorized in this response. Only incident-learning/protocol-governance recording is permitted until the response ends.
