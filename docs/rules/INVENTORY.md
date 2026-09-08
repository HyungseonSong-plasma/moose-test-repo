# MOOSE/QPX Rule Inventory

**Status:** canonical inventory index  
**Purpose:** locate dormant rule owners and phase packs without loading their full contents.

This file is an index, not a rulebook. Do not copy full rule text here. The canonical rule remains in its owner document.

## Inventory metadata

Each inventory entry should identify:

```text
Pack / owner
Primary phase
Trigger
Priority
Approximate load cost
Prevention maturity where relevant
Related incident classes or symptoms
Dependencies / conflicts when material
```

Load cost is a repository heuristic from `docs/protocols/rule_working_set.md`, not a model capability measurement.

## Core pack

| Owner | Phase | Trigger | Priority | Load cost | Notes |
|---|---|---|---|---:|---|
| `OPERATING_CORE.md` | ALL | every repository work item | critical | 5-8 | Always-active invariants only |
| `PROTOCOL_INDEX.md` | ALL | every routed task | critical | 2 | Router; selects phase/obligation owners |
| `docs/protocols/rule_working_set.md` | ALL | bootstrap or phase transition | critical | 2 | Controls load/unload, not technical behavior |

## Phase packs

| Pack | Canonical owner(s) | Primary trigger | Approx. load cost | Typical unload signal |
|---|---|---|---:|---|
| `PLAN` | `docs/protocols/problem_solving.md` + router | bounded objective / diagnosis framing | 5-8 | implementation/research/validation phase becomes primary |
| `RESEARCH` | Researcher/Validator sections of `docs/protocols/problem_solving.md` | material source/model/provenance/representation uncertainty | 5-8 | source/model contract accepted or uncertainty no longer path-changing |
| `IMPLEMENT` | `docs/protocols/coding.md` | code/harness/script/checker modification | 5-8 | implementation artifact stabilized and execution/validation becomes primary |
| `VALIDATE` | `docs/protocols/validation.md` | executable batch, runtime evidence, PASS/FAIL claim | 7-10 | acceptance/hold established and closure becomes primary |
| `CLOSE` | `docs/protocols/metrics_closure.md` | closure, retrospective, incident-learning or enforcement review | 5-8 | bounded work closed or next technical phase begins |
| `MUTATE` | `docs/protocols/repository_mutation.md` | actual GitHub/file/issue/ref write step | 3-6 | immediately after mutation and read-back verification |
| `SCIENTIFIC_EXECUTION` | `docs/protocols/scientific_execution.md` | claim depends on intent/regime preservation across model/numerical/runtime/observation layers | 4-7 | ontology link obligations resolved or no executable scientific claim remains |

`MUTATE` is normally a short-lived adjacent pack, not a whole-development-phase pack.

## Temporary diagnostic inventory

Load only when a matching signal appears.

| Owner / source | Trigger | Typical incident surface | Default action |
|---|---|---|---|
| `docs/knowledge/TROUBLESHOOTING_INDEX.md` | known recurring symptom/signature | known reusable failures | retrieve matching entry only |
| `docs/incidents/` | symptom requires prior RCA/evidence | incident-specific reproducer/root cause | load only relevant incident(s) |
| `docs/metrics/incidents/learning_ledger.md` | prevention-learning comparison or recurrence decision | known recurrence / enforcement failure | load relevant rows/metrics only |
| `docs/metrics/incidents/snapshots/` | trend/root-cause distribution analysis | aggregate operational risk | load requested reporting windows only |

## Specialized validation inventory

These are normally selected from `docs/protocols/validation.md` by trigger rather than preloaded as separate packs.

| Rule area | Trigger examples | Related incident surface |
|---|---|---|
| Semantic equivalence / representation | numeric serialization, exact-vs-tolerance, aggregation/state identity | Validation Harness & Classifier |
| Temporal observation semantics | transient CSV, initial row, old/current state, derived quantities | Validation Harness & Classifier / Boundary Timing |
| Parser namespace preflight | parsed functor/material symbols | Parser Reserved Symbol |
| Provider ownership preflight | shared material/functor producer graph | Property Ownership Duplicate |
| Environment/JIT preflight | JIT/cache/binary/environment-sensitive construction | JIT & Environment Failures |
| Numerical contract/runtime-semantic gate | convergence, tolerance floor, adaptivity/coupling/timestep regime | Solver Convergence / Tolerance / Active-Set |

## Prevention maturity reference

When incident learning is material, use the strongest evidence-backed maturity from `MET-22`:

```text
DOCUMENTED
TRIGGERED
MACHINE_CHECKED
MUTATION_TESTED
IMPOSSIBLE_BY_CONSTRUCTION
```

The inventory may record this maturity for frequently reused controls, but `docs/protocols/metrics_closure.md` remains the canonical semantic owner.

## Inventory maintenance

Add an inventory entry when a reusable canonical owner becomes difficult to discover by phase/trigger. Do not add a new entry merely because a rule gains another example.

Remove or merge inventory entries when:

```text
owners are duplicated
triggers overlap without semantic distinction
a specialized rule becomes a subsection of an existing owner
an obsolete compatibility guide no longer needs routing visibility
```

The inventory should improve retrieval precision while remaining substantially smaller than the documents it indexes.
