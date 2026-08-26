# Problem-Solving Protocol

**Status:** canonical procedure  
**Scope:** MOOSE/QPX technical issues and bounded child work items  
**Purpose:** reduce external validation rounds by doing high-value research, framing, and discrimination before user-local runtime execution.

## PS-01 — Phase 0 problem framing

Before spending an EVR, define:

```text
Closure claim
Known-good control
Primary unknown classes
Dependency graph
Research questions
Expected evidence/signatures
Prospective EVR budget: 0/3
```

If the work boundary cannot be stated clearly, split or redefine the issue before runtime.

## PS-02 — Role routing

Use the Manager as orchestrator.

Researcher is required for material questions involving source truth, literature, provenance, model alternatives, upstream state dependencies, or representation adequacy.

Validator is required for adequacy, acceptance, test sufficiency, closure, false-PASS risk, and promotion decisions.

Canonical mixed flow:

```text
Manager
  -> Researcher: establish source/model truth
  -> Validator: decide adequacy/applicability/acceptance
  -> implementation/batch only after the decision
```

One material Researcher->Validator decision attributable to the work item counts as one RVR under `metrics_closure.md`.

## PS-03 — Hypothesis register

Before modifying code, enumerate materially plausible explanations. Typical classes:

```text
infrastructure/build
environment/runtime identity
harness/construction
reference/source data
transformation/unit/sign/indexing
resolution/precedence/aliasing
representation adequacy
solver/convergence/scaling
coupling/residual participation
boundary/interface
discretization/timestep
implementation parity
physics/model formulation
```

For each hypothesis, predeclare what observation would support or reject it.

## PS-04 — Known-good control is mandatory when available

Run a previously accepted control alongside a candidate whenever practical.

```text
candidate FAIL + control PASS -> candidate-specific class
candidate FAIL + control FAIL -> environment/build/global class
```

A historical control is especially important after rebuilds, environment changes, or long pauses.

## PS-05 — Test-independence audit

Before execution, ask:

```text
If T1 fails, do T2/T3 still provide independent information?
```

If not, do not count them as parallel discriminators. Prefer orthogonal controls over dependency ladders whose descendants inherit the same primitive failure.

The first batch should maximize independent information gain, not raw test count.

## PS-06 — Predictive pre-mortem

Assume the primary candidate fails. Add cheap, deterministic, independent branch tests for the likely next questions before external execution.

At minimum consider:

```text
harness/construction
known-good baseline
source/reference
representation
implementation parity
environment/build
solver/convergence
physics/model
```

Predicted result signatures should be written before execution whenever practical.

## PS-07 — Three-EVR state machine

The default budget for one bounded work item is:

```text
EVR #1 = broad discrimination
EVR #2 = targeted confirmation / fix validation
EVR #3 = canonical production regression
```

### EVR #1
Goal: establish PASS or one dominant root-cause class.

The batch should include the applicable P0-P3 path from `validation.md`, known-good control, candidate, independent oracle/reference, predeclared fail branches, and environment/executable identity.

Valid terminal classes include:

```text
PASS
SOURCE_MODEL_FAIL
REFERENCE_DATA_FAIL
REPRESENTATION_ADEQUACY_FAIL
HARNESS_OR_CONSTRUCTION_FAIL
ENVIRONMENT_OR_BUILD_FAIL
SOLVER_CONVERGENCE_FAIL
IMPLEMENTATION_PARITY_FAIL
PHYSICS_MODEL_FAIL
```

`UNKNOWN_FAIL` after EVR #1 is a batch-design warning and requires Validator review before EVR #2.

### EVR #2
Reserved for the single diagnosed class from EVR #1. Change only that class unless new evidence falsifies the diagnosis.

Pattern:

```text
one diagnosed class
  -> one targeted fix
  -> direct regression
  -> negative control/mutation
  -> representative original case
```

Do not stack speculative changes across physics, solver, parser, and environment in the same confirmation round.

### EVR #3
Canonical closure regression only. Include production path, representative regime matrix, boundary/edge case when relevant, physical/analytic invariant, known-good non-regression, and validator negative controls.

If EVR #3 fails, do not automatically consume EVR #4 under the same unchanged scope. Instead:

```text
A. return to Researcher->Validator if a source/model assumption is doubtful;
B. split a new independent child issue if a new failure class emerged;
C. open/promote a framework/harness/environment incident when appropriate;
D. redefine the bounded work claim if the original scope was too broad.
```

## PS-08 — Coupled nonlinear convergence triage

For coupled problems, put convergence sensitivity in EVR #1 whenever a dominant subsystem can hide a smaller one, exact IC passes while zero/approximate IC fails, or a physical invariant is wrong despite solver convergence.

High-value controls:

```text
default convergence
forced additional nonlinear correction when supported
tighter/effectively disabled relative tolerance
subsystem/reference residual convergence
```

Interpret physical invariants, not only process return codes.

Typical signature:

```text
default fails invariant + forced/tight variants recover
  -> premature/global convergence criterion moves up sharply
```

A diagnostic workaround such as forced iterations is not automatically the production design. Prefer framework-native subsystem-aware convergence when validated.

## PS-09 — Coupling localization

When subsystems work alone but fail together, construct an ON/OFF matrix that changes one coupling axis at a time. If one row/column remains healthy, remove that subsystem from the active suspect list until new evidence contradicts it.

For transient conservation failures, report the discrete accounting identity numerically:

```text
inventory change / dt
  = volume sources
  - sinks
  - boundary outflux
  + boundary influx
```

If a diagnostic flux exists but inventory does not contain it, test residual participation and convergence before changing its physical coefficient.

## PS-10 — Representation-adequacy gate

Before collapsing an upstream model into a simpler table/runtime schema, inventory every independent state variable and branch used by the source model.

Example:

```text
source: Q = Q(T, Te, ne, interaction_type)
target: Q = table(T)
```

Hold represented variables fixed and vary omitted variables independently. If the source changes beyond tolerance, classify `REPRESENTATION_ADEQUACY_FAIL` and change architecture/interface rather than densifying the inadequate table.

## PS-11 — Evidence hierarchy

Prefer, in order:

```text
analytic identity matched by measurement
independent recovery perturbations
orthogonal controlled experiment
conservation/invariant accounting
framework/source contract confirmed in source
circumstantial symptom correlation
code-appearance intuition
```

Declare a root cause only with sufficient independent evidence for the claim.

## PS-12 — Source inspection must answer a concrete question

Do not browse framework internals broadly to see what looks suspicious. First use black-box discrimination to narrow the question, then inspect only the source path necessary to answer it.

## PS-13 — Incident-to-algorithm learning

When a real failure is caught:

```text
preserve chronological incident evidence
extract the reusable symptom -> discriminator mapping
promote reusable checks to validation preflight or troubleshooting knowledge
update this protocol only when the solving algorithm itself changes
```

## PS-14 — Optimization target

Primary prospective target for bounded work:

```text
EVR <= 3
DBR <= 2
RWR = 0
closure quality unchanged
```

RVR is not minimized. Its purpose is to move uncertainty earlier when doing so reduces downstream EVR/DBR/RWR or reopening risk.

## PS-15 — Issue sizing and decomposition

Execution issues should be small enough that one bounded closure claim can plausibly complete inside one prospective 3-EVR budget.

Preferred execution boundary:

```text
1 closure claim
1 bounded subsystem or coupling edge
1 prospective EVR budget <= 3
ideally 1 production decision
complexity C1-C3 when practical
```

Treat C4 primarily as architecture/planning/tracking scope. Before technical runtime begins, decompose a C4 item into bounded C1-C3 successor issues when it contains multiple serial closure claims.

Strong split signals include:

```text
"finish A, then implement B, then validate C"
source/model uncertainty and runtime integration are separable
multiple independent coupling edges require separate acceptance
one stage can close while later stages remain blocked
EVR #3 would only finish an intermediate stage rather than the issue claim
```

Do not keep a large parent open merely to accumulate unrelated downstream execution metrics. A parent may be closed as `DECOMPOSED_PARENT` after its validated history and successor links are recorded. This is not a claim that unfinished downstream physics is technically complete.

Successor issues start with their own issue-local metrics and their own prospective `0/3` EVR budget. Historical metrics remain on the original parent and are not copied into successors.