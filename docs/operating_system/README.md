# MOOSE/QPX Operating System Versions

**Current version name:** Calvin  
**Current baseline date:** 2026-09-01  
**Status:** active experimental operating baseline

This directory records named operating-system baselines so later revisions can be compared against earlier ones using observed execution, routing, incident, and rule-activation data.

## Current operating system

`Calvin` is the first named baseline of the Adaptive Rule Working Set architecture.

Its defining objective is:

```text
minimum active rule load
subject to
acceptable decision, prevention, and closure quality
```

The complete live behavior remains owned by the canonical operating documents (`BOOTSTRAP.md`, `OPERATING_CORE.md`, `PROTOCOL_INDEX.md`, and the routed protocols). Version logs are historical comparison records; they do not override live canonical rules.

## Version log

| Baseline date | Version name | Record | Status |
|---|---|---|---|
| 2026-09-01 | Calvin | `versions/2026-09-01_calvin.md` | current baseline |

## Versioning discipline

When the operating system is materially upgraded:

1. create a new immutable dated version log rather than rewriting an older baseline;
2. update the current version name/date in this index;
3. state the architectural or policy changes relative to the preceding baseline;
4. compare observed metrics only when denominators and measurement coverage are compatible;
5. distinguish architectural changes from model-version changes, repository changes, and workload-mix changes.

A version name identifies an operating-system baseline, not a claim that every rule or activation pattern in that baseline has already been validated as canonical.