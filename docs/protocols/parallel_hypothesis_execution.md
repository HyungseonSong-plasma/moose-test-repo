# Parallel Hypothesis Execution Protocol

**Status:** proposed protocol / design branch
**Scope:** scientific diagnostics whose independent hypotheses can be evaluated from one immutable repository snapshot
**Purpose:** reduce wall-clock diagnosis time without weakening provenance, controls, validation gates, or repository-mutation safety.

This protocol extends `problem_solving.md` PS-03/PS-05 and `repository_mutation.md` RM-12. It does not authorize parallel canonical mutation.

## PHE-01 — Parallelize hypotheses, not arbitrary tasks

A parallel batch is justified only when each matrix entry answers a distinct pre-registered question and remains informative if another entry fails.

For each hypothesis record:

```text
hypothesis_id
claim
candidate mutation
support signature
reject signature
known confounders
```

Dependency ladders are not counted as independent parallel discriminators.

## PHE-02 — One immutable base SHA

Every job in one hypothesis batch must checkout the same explicit `base_sha`.

```text
workflow definition head may move
experiment base_sha must not move
```

Each result must report both the workflow event SHA and the checked-out experiment base SHA. A job is invalid if the checked-out HEAD differs from the declared base SHA.

## PHE-03 — Runtime-only diagnostic mutation

Hypothesis jobs must construct diagnostic inputs in the runner workspace. They must not commit experiment-specific changes, move refs, edit issues, or change canonical repository state.

Allowed:

```text
checkout immutable base_sha
build exact base_sha
construct temporary diagnostic input
run bounded discriminator
write logs / JSON / artifacts
```

Not allowed inside hypothesis jobs:

```text
commit candidate input
push branch
move main
edit canonical physics source
production promotion
```

This keeps RM-12 canonical mutation locks orthogonal to matrix execution.

## PHE-04 — Shared-state rule

Parallel agents share evidence, not mutable repository state.

Each matrix job owns an isolated workspace and produces an immutable evidence artifact. Jobs must not depend on another matrix job's filesystem or branch mutation.

## PHE-05 — Within-job controls

When runner-to-runner variance can contaminate the measurement, each hypothesis job carries its own controls on the same runner.

For Issue #224 memory attribution the required sequence is:

```text
production_before
candidate
all_57_deferred_low_memory_control
production_after
```

Every runtime is a fresh process. The production controls establish local drift; the all-57-deferred case verifies the accepted low-memory positive control on the same environment.

Historical controls may supplement but do not replace required local controls when machine variance is material.

## PHE-06 — Matrix fan-out

Use one workflow run with a matrix over hypothesis IDs. A workflow-level concurrency group may prevent duplicate batch runs, but it must not serialize sibling matrix jobs.

Recommended pattern:

```yaml
strategy:
  fail-fast: false
  max-parallel: 6
  matrix:
    hypothesis: [H1, H2, H3, H4, H5, H6]
```

`fail-fast: false` is required so one construction/runtime failure does not destroy independent evidence from the remaining hypotheses.

## PHE-07 — Resource isolation

Parallel execution is permitted only when each job has an independent runner allocation. Do not place multiple R2 memory experiments concurrently inside one runner/VM/container host if they can contend for the same physical memory and invalidate RSS attribution.

For GitHub-hosted runners, one matrix job per hosted runner satisfies the intended isolation model. For self-hosted runners, labels and capacity controls must guarantee equivalent isolation.

## PHE-08 — Evidence contract

Each hypothesis artifact must contain at least:

```json
{
  "schema_version": 1,
  "issue": 224,
  "hypothesis_id": "H1",
  "base_sha": "...",
  "workflow_event_sha": "...",
  "physics_opt_sha256": "...",
  "cases": {
    "production_before": {},
    "candidate": {},
    "all_57_deferred": {},
    "production_after": {}
  },
  "decision": {
    "production_control_drift": {},
    "candidate_comparison": {},
    "low_control_comparison": {},
    "candidate_classification": "...",
    "low_control_classification": "...",
    "promotion_authorized": false
  }
}
```

Authoritative measurements, guards, run identity, and artifact digest remain part of the governed evidence chain.

## PHE-09 — Measurement vs interpretation

Experiment jobs classify only their measured discriminator. Cross-hypothesis root-cause interpretation belongs to a later evidence-arbitration step.

Example:

```text
job statement: H1 candidate restored production-like high-water
not allowed: H1 proves MOOSE QP reinit is the root cause
```

A root-cause claim still requires the evidence hierarchy in PS-11.

## PHE-10 — Failure classification

A red matrix cell does not invalidate sibling cells automatically.

Classify each independently:

```text
P0 -> harness/construction
P1 -> implementation/static contract
P2 -> input/interface/preflight
P3 -> bounded runtime/scientific discriminator
```

Only shared build/environment evidence that falsifies the batch identity can invalidate the entire matrix.

## PHE-11 — Adaptive rounds

After one fan-out round:

```text
fan-out -> measure -> arbitrate -> prune -> next fan-out
```

The coordinator removes hypotheses contradicted by evidence and designs the smallest next orthogonal discriminator for unresolved branches. Do not brute-force all permutations when one round has already collapsed the hypothesis space.

## PHE-12 — Promotion gate

Parallel diagnostic success never authorizes production promotion by itself.

Promotion requires a separate canonical decision and the normal exact-head validation path. Diagnostic changes such as deferred schedules or `evaluation_type=CELL_AVERAGE` remain diagnostic-only unless independently validated for production semantics.

## Issue #224 C7 reference batch

The first reference implementation uses six hypotheses:

```text
H1 constant_integral      domain_volume / carrier_one only
H2 primitive_average     electron_pressure_avg / p only
H3 parsed_ad_integral    n_e_inventory / n_e_physical only
H4 lookup_average        electron_mobility_avg / electron_mobility only
H5 cross_type_pair       domain_volume + electron_pressure_avg
H6 cell_average_path     all 57 INITIAL, evaluation_type=CELL_AVERAGE
```

For H1-H5, all other members of the accepted 57-object `element_aggregate` family are deferred from INITIAL execution. H6 preserves the production execution schedule and changes only the diagnostic evaluation path.

All six are R2, `num_steps=0`, fresh-process GNU `/usr/bin/time -v` measurements with no physical timestep and no linear solve.

## Operating principle

```text
parallelize independent hypotheses
share immutable evidence
isolate runner resources
keep canonical state immutable during fan-out
centralize interpretation after measurement
```
