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
