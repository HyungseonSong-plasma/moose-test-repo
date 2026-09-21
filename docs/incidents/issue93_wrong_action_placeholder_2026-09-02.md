# Issue #93 repository mutation wrong-action incident — 2026-09-02

## Intended action

```text
resource: issue
exact target: #93
intended mutator: GitHub.update_issue
purpose: record Issue #93 EVR2 result and J3 decision
```

## Actual wrong action

A file mutation was invoked instead:

```text
mutator: GitHub.update_file
path: __noop__
content: x
commit message: noop
commit: bb9d5e2af6b5b7d18bff508021d3f0485c23091a
```

This violated the repository mutation resource-class, target, adjacent-call, exact-mutator, and placeholder guards.

## Repair

The accidental file was read back and removed with the exact `delete_file` structural opcode:

```text
removed path: __noop__
repair commit: 148e2bf9d15133bb3e5f44ccdaf6e66718b678d5
post-repair verification: path absent / 404
```

Shared history was preserved; no history rewrite was attempted.

## Root cause

The business intent and response mutation class were `issue`, but the final generated recipient was a file mutator carrying placeholder target/SHA/message values. Existing intent and payload guards did not prevent recipient substitution at the final invocation boundary.

## Preventive action

`docs/protocols/repository_mutation.md` now contains RM-13, a literal recipient + forbidden-placeholder call gate. The exact selected callable must match the frozen mutator/resource class and placeholder/probe tokens such as `__noop__`, `deadbeef`, `noop`, `probe`, `dummy`, or `placeholder` hard-stop the call before invocation.

## Circuit breaker

RM-09A was triggered. The originally intended #93 business mutation and dependency synchronization were deferred to a fresh response context.
