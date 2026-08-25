# Multiphysics Problem-Solving Protocol

**Status:** living guide  
**Scope:** MOOSE/QPX multiphysics debugging, verification, and incident isolation  
**Purpose:** reduce time-to-root-cause by turning successful diagnostic patterns into a reusable protocol.

## 1. Core principle

Debug coupled multiphysics problems by **reducing uncertainty in the cheapest, highest-information order**.

Prefer controlled black-box diagnostics before source patches or framework-internal investigation.

The default order is:

```text
infrastructure
    -> subsystem localization
    -> conservation / invariant accounting
    -> convergence sensitivity
    -> parameter sweep / analytic signature
    -> framework/source instrumentation
    -> production change
```

Do not jump directly from a failing integrated case to a source-code modification unless the preceding stages already isolate the mechanism.

---

## 2. Problem classes

Classify the symptom before choosing a diagnostic path.

| Class | Typical symptom | First question |
|---|---|---|
| Infrastructure | executable does not start, missing library, corrupt binary | Did the physics solver actually run? |
| Solver/convergence | solve reports convergence but physical invariant is wrong, or line search diverges | Is the convergence criterion appropriate for every coupled subsystem? |
| Coupling | each subsystem works alone but fails when coupled | Which coupling edge introduces the failure? |
| Physics/formulation | stable/converged result violates expected physics | Is the equation, sign, flux, or closure wrong? |
| Discretization | mesh/order/timestep strongly changes behavior | Is the discrete operator consistent and converged? |
| Boundary/interface | bulk is correct but conservation/directionality fails at a boundary | Is the boundary flux participating in the residual exactly as expected? |

A test failure may move between classes as evidence accumulates. Record that change explicitly.

---

## 3. Stage 0 — Infrastructure gate

Before interpreting any test as a physics regression, verify:

- executable integrity;
- architecture/platform compatibility;
- dynamic libraries and runtime environment;
- input file is actually parsed;
- solver reaches the nonlinear/linear solve;
- output belongs to the intended executable/source revision.

### Rule

```text
solver not reached -> infrastructure incident
solver reached     -> physics/solver investigation may begin
```

Never classify missing shared libraries, corrupted ELF files, or wrong runtime paths as physics failures.

---

## 4. Stage 1 — Establish the invariant and known-good baseline

Define what must remain true independent of implementation details.

Examples:

- global mass conservation;
- charge conservation;
- flux directionality;
- positivity;
- expected centroid shift;
- analytic Laplace/Poisson solution;
- symmetry;
- prescribed-field reference result.

Separate tests into:

### Canonical
Permanent regressions. These encode invariants that must always pass.

### Diagnostic
Temporary or incident-isolation tests. These may fail while the mechanism is being investigated.

Do not weaken canonical acceptance criteria to accommodate a new implementation.

---

## 5. Stage 2 — Orthogonal subsystem localization

Construct the smallest matrix that turns coupled features ON/OFF independently.

Example pattern:

```text
                 initial state A    initial state B
bulk only             test               test
wall only             test               test
```

Good localization matrices:

- change one axis per physical mechanism;
- preserve all unrelated parameters;
- include at least one known-good control;
- make every matrix cell interpretable before execution.

### Decision rule

If one row/column is entirely healthy, remove that subsystem from the active suspect list until new evidence contradicts it.

Do not continue inspecting healthy subsystems merely because they participate in the full application.

---

## 6. Stage 3 — Conservation and residual accounting before source inspection

When a transient solution is wrong, write the discrete accounting identity explicitly.

Generic form:

```text
inventory change / dt
    = volume sources
    - volume sinks
    - boundary outflux
    + boundary influx
```

For every first-step incident, compare the measured inventory change against each independently reported contribution.

### Required outputs

Prefer numeric evidence such as:

```text
dm
-dm/dt
source rate
surface-loss rate
migration rate
balance error
```

A PASS/FAIL label alone is insufficient for root-cause work.

### Rule

If the final diagnostic flux exists but the inventory update does not contain it, first investigate **residual participation and convergence**, not the physical coefficient.

---

## 7. Stage 4 — Convergence triage rule

This stage is mandatory for coupled problems in which:

- one subsystem has a much larger initial residual than another;
- the solver reports convergence while a smaller subsystem violates an invariant;
- the final field is correct but another coupled variable has a first-step balance error;
- exact initial conditions pass while approximate/zero initial conditions fail.

Run the following before source modification:

```text
A. default convergence settings
B. force one additional nonlinear correction (typically nl_forced_its = 2)
C. strongly tighten or effectively disable the relative tolerance
```

Compare **physical invariants**, not just process return codes.

### Interpretation

| Result | Interpretation |
|---|---|
| default fails, forced2 passes | default nonlinear convergence is premature |
| default fails, tight relative tolerance passes | relative convergence criterion is premature |
| forced2 and tight tolerance both pass | strong evidence that physics/coupling implementation is valid but global convergence is insufficient |
| all variants fail identically | move on to residual participation, discretization, or source-level investigation |
| forced extra iterations introduce a new solver failure | treat that failure separately; do not erase the evidence from earlier converged iterations |

### Generalized lesson from M5 wall migration

A large electrostatic residual can dominate the global nonlinear norm and allow the solver to declare relative convergence before a smaller species equation has completed its coupled Newton correction.

Therefore:

> If the converged dominant field is correct but a secondary physics invariant is wrong, test subsystem-sensitive convergence before changing the physics.

---

## 8. Stage 5 — Parameter sweep and analytic signature

When two or more mechanisms remain plausible, sweep one control parameter while keeping all other quantities fixed.

Good sweep variables include:

- initial-condition amplitude;
- coupling strength;
- timestep;
- mesh spacing;
- mobility/conductivity scaling;
- boundary-field magnitude.

### Requirements

1. Define expected qualitative/quantitative patterns before running the sweep.
2. Change only one independent variable.
3. Preserve raw values, not just classification labels.
4. If possible, derive a reduced analytic model.

A distinctive analytic signature is often more powerful than additional source inspection.

### Example lesson

The M5 wall-migration initial-potential sweep produced values exactly matching a single Newton linearization of the bilinear wall term. That signature exposed premature nonlinear termination much faster than further wall-physics modification would have.

---

## 9. Stage 6 — Source/framework investigation only after black-box discrimination

Inspect framework internals when controlled tests cannot distinguish the remaining hypotheses.

Typical targets:

- state selection (`current` vs `old`);
- AD derivative connectivity;
- functor caching/clearance;
- boundary `FaceArg` construction;
- FV gradient reconstruction;
- residual/Jacobian assembly;
- convergence object behavior;
- scaling and reference residuals.

### Source-inspection rule

Every source inspection should answer a concrete question produced by a prior test.

Bad:

```text
Read several framework classes to see what looks suspicious.
```

Good:

```text
Test shows exact IC passes and zero IC fails.
Question: does the wall BC evaluate the potential at old state or current state?
Inspect only the state-selection path needed to answer that question.
```

---

## 10. Stage 7 — Production fix selection

A diagnostic workaround is not automatically a production design.

Examples:

- `nl_forced_its = 2` may prove premature convergence, but forcing a fixed number of iterations is not necessarily the best permanent solution;
- an extremely tight global `nl_rel_tol` may prove the mechanism, but can be expensive or fragile;
- smoothing a branch may be diagnostic without being physically or numerically justified as the production closure.

Select production fixes using:

1. correctness;
2. robustness across regimes;
3. computational cost;
4. framework-native mechanisms where possible;
5. compatibility with canonical tests.

For multiphysics convergence, prefer subsystem-aware/reference residual convergence over arbitrary fixed iteration counts when supported and validated.

---

## 11. Evidence hierarchy

Use the strongest available evidence first.

From strongest to weakest:

1. analytic identity matched by measured output;
2. orthogonal controlled experiment;
3. independent perturbations producing the same recovery;
4. conservation/invariant accounting;
5. framework contract confirmed in source;
6. circumstantial symptom correlation;
7. intuition based only on code appearance.

Do not promote a hypothesis to root cause on code appearance alone.

---

## 12. Diagnostic experiment template

Every new diagnostic should specify:

```text
Question:
    What single hypothesis is being tested?

Invariant setup:
    What is held fixed?

Perturbation:
    What one thing changes?

Measured quantities:
    Which numeric outputs distinguish the hypotheses?

Predicted outcomes:
    If A -> conclusion X
    If B -> conclusion Y

Stop condition:
    What result is sufficient to reject or support the hypothesis?
```

If the predicted outcomes are not written before the test, the experiment is underspecified.

---

## 13. Incident-to-guide promotion rule

Incident logs preserve history. This guide preserves reusable knowledge.

At incident closure:

1. keep the full chronological evidence in the incident log;
2. extract only generalized, reusable rules;
3. add them to this guide;
4. remove incident-specific variable names unless they are useful examples;
5. link back to the incident when provenance matters;
6. add or promote a canonical regression for the fixed invariant.

Do not turn this guide into a chronological incident dump.

---

## 14. Update policy

This document is a living protocol.

Update it when one of the following occurs:

- a diagnostic sequence proves substantially faster than the current recommended order;
- a repeated failure pattern appears in more than one incident;
- a previously recommended diagnostic produces misleading conclusions;
- a new MOOSE-native mechanism improves convergence/debugging;
- an incident invalidates an existing rule;
- a new invariant becomes important enough to standardize.

Every update should state:

```text
What changed?
Why?
Which incident/evidence motivated it?
Does it replace or refine an existing rule?
```

Prefer refinement over accumulating contradictory rules.

---

## 15. Fast path checklist

For a new coupled MOOSE regression, use this sequence by default:

```text
[ ] 1. Confirm solver/runtime actually reaches physics
[ ] 2. Identify known-good canonical baseline
[ ] 3. Write the governing conservation/invariant identity
[ ] 4. Build minimal orthogonal subsystem matrix
[ ] 5. Record numeric residual/conservation contributions
[ ] 6. Run default vs forced2 vs tight-relative-tolerance convergence triage
[ ] 7. If still ambiguous, sweep one parameter and derive expected signature
[ ] 8. Only then inspect framework/source internals
[ ] 9. Validate production fix against canonical + incident regression
[ ] 10. Promote reusable lesson into this guide
```

---

## 16. Current reusable lessons

### 16.1 Residual-floor rule

Before tightening an absolute nonlinear tolerance, measure the numerical residual floor. A tolerance below the floor can produce false line-search/divergence incidents even when the algebraic state is already converged.

### 16.2 Convergence-triage rule

When the final dominant field is correct but a secondary coupled invariant is wrong, test `default / forced2 / tight relative tolerance` before changing physics.

### 16.3 Invariant-over-return-code rule

A solver return code does not determine physical correctness. Always compare the invariant itself.

### 16.4 One-change-per-diagnostic rule

A diagnostic that changes multiple controls cannot uniquely identify a cause. Keep one independent perturbation per experiment whenever possible.

### 16.5 Healthy-subsystem exclusion rule

Once an orthogonal matrix clears a subsystem, stop modifying it unless new evidence reopens it.

### 16.6 Analytic-signature rule

If a reduced analytic model predicts a distinctive numeric pattern and the sweep matches it, treat that as high-grade root-cause evidence.
