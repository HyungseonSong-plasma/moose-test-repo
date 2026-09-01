# MOOSE/QPX Operating Core

**Status:** canonical  
**Scope:** always-active operating invariants for this repository  
**Purpose:** keep the always-loaded rule set small, stable, and unambiguous.

This file contains only invariants that apply across essentially every MOOSE/QPX work item. Conditional behavior is loaded through `PROTOCOL_INDEX.md` and `docs/protocols/rule_working_set.md`.

## Canonical always-active invariants

### CORE-01 — Team boundary
This repository is for MOOSE/QPX work. Do not perform SOL-team or `sol-adapter-moose` work here unless the user explicitly changes scope.

### CORE-02 — Meeting means no mutation
When the user says `meeting`, discuss and plan only. Do not mutate GitHub, files, issues, or production artifacts.

### CORE-03 — Approval authorizes execution
`승인` / `approve` authorizes the agreed plan. `resume` authorizes continuation of the currently agreed work package. Discussion alone does not authorize execution.

### CORE-04 — Work identity and current state
Technical execution must be attributable to a concrete issue or bounded work item with a closure claim. For active/open work, the issue body/current status block is the canonical STATE record; comments are historical evidence unless the body is explicitly stale and being repaired.

### CORE-05 — Runtime evidence authority
Canonical QPX runtime evidence comes from the user's real local `qpx-opt`. Static/CI evidence may support construction checks but must not be promoted to QPX physics PASS/FAIL evidence when the real executable path was not exercised.

### CORE-06 — One canonical owner per rule
Do not duplicate canonical procedure text across issue bodies, comments, READMEs, guides, or protocols. Reference the Rule ID or canonical owner. When a rule changes, update its one owner and route to it.

### CORE-15 — Adaptive rule working set
Do not preload the repository's complete rule graph. Maintain the smallest relevant working set:

```text
CORE
+ current PHASE PACK
+ only triggered TEMPORARY DIAGNOSTIC material
```

Load, unload, sizing heuristics, phase transitions, and inventory lookup are defined in `docs/protocols/rule_working_set.md`. Rule accumulation is not a substitute for correct routing.

### CORE-16 — Intent-preserving scientific validity
A scientific computation is valid only when the actual execution preserves the scientific intent and regime required by the closure claim. Parser acceptance, return code, solver convergence, or output existence alone are never sufficient proof of scientific validity.

When this cross-layer contract is material, load `docs/protocols/scientific_execution.md`. Model/regime meaning is delegated to `docs/protocols/problem_solving.md`; execution/evidence sufficiency is delegated to `docs/protocols/validation.md`.

## Conditional-rule ownership map

The following former always-active concerns remain canonical but are no longer permanently loaded. Their legacy CORE IDs are retained here only for compatibility and routing.

| Legacy ID | Concern | Canonical phase owner |
|---|---|---|
| CORE-07 | Construction failure is not physics failure | `docs/protocols/validation.md` |
| CORE-08 | P0 -> P1 -> P2 -> P3 validation order | `docs/protocols/validation.md` |
| CORE-09 | Research before guessing material source/model facts | `docs/protocols/problem_solving.md` |
| CORE-10 | Validator owns sufficiency / false-PASS decisions | `docs/protocols/validation.md` |
| CORE-11 | New failure -> reusable evidence / recurrence learning | `docs/protocols/metrics_closure.md` + incident/knowledge owners |
| CORE-12 | 3-EVR bounded-work protocol | `docs/protocols/problem_solving.md` |
| CORE-13 | Closure-quality guardrail | `docs/protocols/metrics_closure.md` |
| CORE-14 | External bundle/path safety | `docs/protocols/validation.md` / `docs/protocols/coding.md` as triggered |

A legacy reference to CORE-07 through CORE-14 means "route to the canonical owner above"; it does not mean the full owner must remain in every active context.

## Always-load sequence

For technical work:

```text
1. read OPERATING_CORE.md
2. read current issue/body/status when work state is material
3. read PROTOCOL_INDEX.md
4. apply docs/protocols/rule_working_set.md
5. load only the current phase owner(s)
6. load incident/knowledge material only when triggered
```

## `moose-test-init` bootstrap

`moose-test-init` is the official cross-chat initialization command. Its one canonical procedure is `BOOTSTRAP.md`.

Do not duplicate the bootstrap algorithm here. On `moose-test-init`, route to `BOOTSTRAP.md`, restore the minimum safe resume context, and then use the adaptive working-set rules for subsequent user turns.