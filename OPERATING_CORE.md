# MOOSE/Physics Operating Core

**Status:** canonical consumer-local core under Paul  
**Purpose:** retain only Physics-specific invariants that cannot be delegated to central Paul rules/skills.

Paul `ESSENTIAL_RULES.md` is loaded before this file during initialization. Do not duplicate those generic rules here.

## Local always-active invariants

### PCORE-01 — Team boundary

This repository is for MOOSE/Physics work. Do not perform SOL Platform or `sol-adapter-moose` work here unless the user explicitly changes scope.

### PCORE-02 — Local mode authority

`meeting` is discussion/planning only and does not authorize repository mutation.

`승인` / `approve` authorizes the agreed plan. `resume` authorizes continuation of the currently accepted work package. Discussion alone does not authorize execution.

### PCORE-03 — Work identity and STATE

Technical execution must be attributable to a concrete issue or bounded work item with a closure claim.

For active/open work, the issue body/current status block is the canonical local STATE record. Comments are chronological evidence unless the body is explicitly stale and being repaired.

### PCORE-04 — Physics runtime evidence authority

Canonical Physics runtime evidence requires provenance-controlled execution of the real `physics-opt` production path.

Governed CI and user-local execution may both be authoritative when source revision, executable identity, dependency/runtime-environment identity, scientific execution contract, and preserved evidence are sufficient for the owning claim.

Static analysis, mocks, checker-only execution, parser acceptance, and `physics-opt --check-input` are not Physics runtime evidence.

Historical `QPX` / `qpx-opt` names may remain in historical records; current runtime ownership uses `Physics` / `physics-opt`.

### PCORE-05 — Intent-preserving scientific validity

A scientific computation is valid only when actual execution preserves the scientific intent and regime required by the claim.

Parser acceptance, return code, solver convergence, or output existence alone are never sufficient proof of scientific validity.

Use `docs/protocols/scientific_execution.md` when cross-layer intent/regime preservation is material, `problem_solving.md` for model/regime meaning, and `validation.md` for evidence sufficiency.

### PCORE-06 — Hierarchical delivery boundaries

For non-trivial development preserve:

```text
Project -> Milestone -> Issue -> Work Batch -> Mutation/Validation Unit
```

A milestone is a capability boundary; an issue is the semantic implementation/rollback boundary; a work batch is an execution boundary; mutation safety remains independent.

Detailed milestone semantics are owned by `docs/protocols/milestone_delivery.md`.

## Paul composition

For technical work:

```text
Paul essential rules
+ this Physics core
+ current issue/STATE
+ one current local semantic phase owner
+ only central skills triggered by the immediate obligation
+ temporary diagnostic evidence only when needed
```

No weighted rule-load threshold or operating metric is part of the live core.

## Initialization

`moose-test-init` routes to `BOOTSTRAP.md`, which delegates generic bootstrap mechanics to the pinned central `session-bootstrap` skill.
