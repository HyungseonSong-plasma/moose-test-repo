# MOOSE/Physics Operating System Versions

**Current version name:** Calvin  
**Current baseline date:** 2026-09-01  
**Reserved successor:** Paul  
**Successor state:** RESERVED  
**Status:** active experimental operating baseline

This directory records named operating-system baselines so later revisions can be compared against earlier ones using observed execution, routing, incident, and rule-activation data.

Current product/runtime naming is `MOOSE/Physics` and `physics-opt`. Immutable historical version records may retain `MOOSE/QPX` or `qpx-opt` when those names describe the system that existed at the time; do not rewrite those historical baselines merely to follow the current rename.

## Current operating system

`Calvin` is the first named baseline of the Adaptive Rule Working Set architecture.

Its defining objective is:

```text
minimum active rule load
subject to
acceptable decision, prevention, and closure quality
```

The complete live behavior remains owned by the canonical operating documents (`BOOTSTRAP.md`, `OPERATING_CORE.md`, `PROTOCOL_INDEX.md`, and the routed protocols). Version logs are historical comparison records; they do not override live canonical rules.

## Reserved successor

`Paul` is reserved for the first materially upgraded operating-system baseline that supersedes Calvin.

Paul is **not active** merely because operating documents continue to evolve. Minor cleanup, routine rule additions, or evidence updates remain Calvin unless an explicit successor promotion is made.

The successor contract is defined in:

```text
docs/operating_system/PAUL_CANDIDATE.md
```

That contract defines material-upgrade criteria, Calvin-to-Paul comparison requirements, promotion evidence, decision states, and the rule for preserving rejected successor experiments.

## Version log

| Baseline date | Version name | Record | Status |
|---|---|---|---|
| 2026-09-01 | Calvin | `versions/2026-09-01_calvin.md` | current baseline |
| future | Paul | `PAUL_CANDIDATE.md` until activation | reserved successor |

## Version lifecycle

Use the following distinction:

```text
Calvin = ACTIVE current baseline
Paul   = RESERVED successor name
```

When a material successor design begins evaluation, Paul may move through:

```text
RESERVED -> CANDIDATE -> SHADOW -> ACTIVE
                         \
                          -> REJECTED
```

`SHADOW` is preferred when practical because it permits comparison against Calvin before changing the current named operating system.

## Versioning discipline

When the operating system is materially upgraded:

1. preserve the preceding immutable baseline;
2. define the limitation/hypothesis motivating the successor;
3. record the successor architecture/policy delta and expected measurable effect;
4. compare observed metrics only when denominators and measurement coverage are compatible;
5. distinguish operating-system changes from model-version changes, repository changes, and workload-mix changes;
6. create a new dated immutable version record only when the successor is explicitly activated;
7. update the current version name/date in this index.

For the Calvin-to-Paul transition specifically, follow `PAUL_CANDIDATE.md`. On activation create:

```text
docs/operating_system/versions/YYYY-MM-DD_paul.md
```

and mark Calvin historical without rewriting `versions/2026-09-01_calvin.md`.

A version name identifies an operating-system baseline, not a claim that every rule or activation pattern in that baseline has already been validated as canonical.