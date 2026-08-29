# MOOSE/QPX Operating Core

**Status:** canonical  
**Scope:** always-active operating invariants for this repository  
**Purpose:** keep the always-loaded rule set small, stable, and unambiguous.

This file contains only rules that apply across essentially every MOOSE/QPX work item. Conditional procedures live under `docs/protocols/` and are loaded through `PROTOCOL_INDEX.md`.

## Rule classes

- **MUST** — invariant; violation is an operating error.
- **PROCEDURE** — algorithm loaded only when its trigger applies.
- **HEURISTIC** — optimization target; may be overridden by evidence.
- **STATE** — current issue/work status; belongs in the issue body, not here.
- **KNOWLEDGE** — reusable prior evidence; belongs in `docs/knowledge/`.

## Canonical MUST rules

### CORE-01 — Team boundary
This repository is for MOOSE/QPX work. Do not perform SOL-team or `sol-adapter-moose` work here unless the user explicitly changes scope.

### CORE-02 — Meeting means no mutation
When the user says `meeting`, discuss and plan only. Do not mutate GitHub, files, issues, or production artifacts.

### CORE-03 — Approval authorizes execution
`승인` / `approve` authorizes the agreed plan. `resume` authorizes continuation of the currently agreed work package. Do not treat discussion alone as execution authorization.

### CORE-04 — Issue-first execution
Technical execution must be attributable to a concrete issue or bounded child work item with a closure claim.

### CORE-05 — Current state comes from the issue body
For active/open work, the issue body is the canonical current STATE record. Issue comments are historical evidence and must not override the current status block unless the body is explicitly stale and is being repaired.

### CORE-06 — Real runtime evidence is user-local QPX
Canonical QPX runtime evidence comes from the user's real local `qpx-opt`. GitHub Actions may support static checks but must not be treated as QPX physics PASS/FAIL evidence when the real executable is absent.

### CORE-07 — Construction is not physics
Any failure before physics execution, including P0/P1/P2 failure, is `HARNESS_OR_CONSTRUCTION_FAIL` (or a narrower infrastructure class), not a physics FAIL.

### CORE-08 — Mandatory validation order
Executable MOOSE/QPX work follows `P0 -> P1 -> P2 -> P3` as defined in `docs/protocols/validation.md`.

### CORE-09 — Research before guessing
Material source/model/provenance/representation uncertainty is routed to Researcher evidence before implementation when it can change the engineering path. Do not guess constants, transport data, source behavior, or model dependencies that can be retrieved.

### CORE-10 — Validator owns sufficiency
Acceptance, closure, test sufficiency, false-PASS risk, negative controls, and promotion decisions require the Validator contract in `docs/protocols/validation.md`.

### CORE-11 — New failure creates reusable evidence
A new material failure class must be recorded as an incident or equivalent issue evidence, reduced to a discriminating reproducer/root cause, fixed with regression coverage, and promoted to `docs/knowledge/` when reusable.

### CORE-12 — Bounded work uses the 3-EVR protocol
Each bounded technical work item uses the prospective external-validation budget defined in `docs/protocols/problem_solving.md`: discriminate, targeted confirmation/fix, canonical regression. Do not automatically proceed to EVR #4 under an unchanged work boundary.

### CORE-13 — Do not weaken closure quality to reduce rounds
Efficiency targets never override canonical regressions, physical invariants, independent evidence requirements, or production-path validation.

### CORE-14 — External bundle path safety
A runner receiving a user-provided executable path must resolve it with `realpath` before changing directories. Delivered runtime bundles should contain execution/analyzer artifacts only unless documentation is explicitly requested.

### CORE-15 — One canonical definition per rule
Do not copy canonical procedure text into issue bodies, comments, README files, or another guide. Reference the Rule ID or canonical protocol path instead. When a rule changes, update its one canonical definition.

### CORE-16 — Intent-preserving scientific execution ontology
A scientific computation is valid only when the actual execution preserves the scientific intent and regime required by the closure claim. Parser acceptance, executable return code, solver convergence, or output-file existence alone are never sufficient evidence of scientific validity.

Treat every executable claim as an ontology chain:

```text
CLAIM
  -> MODEL
  -> NUMERICAL REGIME
  -> FRAMEWORK-EFFECTIVE CONFIGURATION
  -> RUNTIME REGIME / TRAJECTORY
  -> OBSERVATION / EVIDENCE
  -> DECISION
```

The chain has the following semantics:

```text
CLAIM      = what the run is intended to establish
MODEL      = retained physics, reduced/averaged physics, validity assumptions, and domain/interface contract
NUMERICAL REGIME = discretization, timestep/cadence, coupling, solver, and scale-resolution intent
FRAMEWORK-EFFECTIVE CONFIGURATION = what QPX/MOOSE actually executes after defaults, overrides, adaptivity, sync, and ownership rules
RUNTIME REGIME = the regime actually traversed during execution, including material state-dependent scale changes
OBSERVATION = whether recorded outputs observe the intended state, time, branch, and invariant
DECISION    = the scientific claim accepted, rejected, held, or re-routed from that evidence
```

Across every material link, distinguish the **semantic object** from its representation and declare identity/ownership/provenance when those affect meaning. Names, symbols, source-code spellings, serialized floating-point values, aggregate statistics, output rows, host constants, and proxy diagnostics are representations; they are not interchangeable merely because they look related.

The validation equivalence relation must be **no stronger than the producing representation guarantees and no weaker than the scientific claim requires**. Before using exact equality or a tight acceptance gate, classify the required relation, for example:

```text
syntax / byte exact
identifier / enum exact
discrete mathematical exact
representation-equivalent numeric
numerical tolerance
convergence / refinement equivalence
physical-model tolerance
```

A representation-only mismatch, wrong aggregation operator, wrong state/time identity, source-vs-host convention mismatch, or proxy/direct-evidence substitution is a validation/contract problem until evidence proves a physics defect. Exact equality is valid only when exact identity is itself guaranteed and required.

No downstream layer may silently contradict an upstream layer. A PASS is allowed only when the evidence needed for the claim demonstrates conformance along every material link. If a material link is unobserved, internally contradictory, leaves the declared regime, changes into an unvalidated regime, or is compared under an unjustified equivalence relation, fail closed as `HOLD`, a construction/runtime-semantic class, `VALIDATOR_SELFTEST_FAIL`, or a new incident rather than allowing a physics PASS.

This ontology is intentionally future-facing: do not attempt to enumerate every possible framework or multiphysics failure in CORE. Define the claim/model/regime explicitly, derive or introspect effective execution controls, preserve semantic identity across representations, monitor the material runtime invariants that can change the regime, and require evidence that the intended contract actually ran.

Responsibility is delegated, not duplicated:

```text
model/scale/coupling meaning and regime boundaries
  -> docs/protocols/problem_solving.md (including PS-23 and Researcher/Validator flow)

semantic equivalence, numerical/framework preflight, runtime-semantic conformance, and evidence sufficiency
  -> docs/protocols/validation.md (including VAL-16 and VAL-21)
```

Automatic recovery is permitted only when it is a predeclared semantics-preserving derived correction. A model/regime transition or unknown contract violation that can change the scientific meaning requires explicit validation/re-routing rather than silent automatic repair.

## Always-load sequence

For every technical response:

```text
1. read OPERATING_CORE.md
2. read current issue body/status block
3. route through PROTOCOL_INDEX.md
4. load only the procedure(s) selected by the router
5. search incidents/knowledge only when the symptom or decision requires it
```

This sequence is itself canonical and is intended to keep the active rule context small.