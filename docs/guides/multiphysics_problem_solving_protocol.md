# Multiphysics Problem-Solving Protocol

**Status:** living guide  
**Scope:** MOOSE/QPX multiphysics debugging, verification, and incident isolation  
**Purpose:** reduce time-to-root-cause by turning successful diagnostic patterns into a reusable protocol.

## 1. Core operating model — parallel hypothesis triage

The default MOOSE-team debugging model is **not** a one-hypothesis-at-a-time funnel.

Use MOOSE's strength in coupled-variable reasoning to generate the plausible hypothesis set up front, then design a compact batch of controlled tests that discriminates among many hypotheses at once.

```text
symptom
   -> invariant / known-good baseline
   -> hypothesis set H = {H1, H2, ... Hn}
   -> discriminating test matrix T = {T1, T2, ... Tm}
   -> batch execution
   -> numeric result signature
   -> eliminate / rank hypotheses
   -> targeted confirmation only if needed
   -> framework/source investigation
   -> production fix
```

The optimization objective is:

> **Maximize hypotheses eliminated per test batch, not the number of tests or the depth of sequential discussion.**

Two rules must be held simultaneously:

1. **Parallel at the batch level:** consider many hypotheses and run several discriminating tests in one execution round.
2. **Controlled at the individual-test level:** each diagnostic case should change one independent control whenever possible.

This preserves causal interpretability without sacrificing speed.

A sequential funnel is still valid when a test is expensive, destructive, or depends logically on a previous result, but it is the fallback rather than the default.

---

## 2. Problem classes

Classify the symptom before building the hypothesis set.

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

## 3. Stage 0 — infrastructure gate

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

Infrastructure checks are normally a prerequisite gate, not one hypothesis among the physics hypotheses.

---

## 4. Stage 1 — establish invariant and known-good baseline

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
Incident-isolation tests. These may fail while the mechanism is being investigated.

Do not weaken canonical acceptance criteria to accommodate a new implementation.

The known-good baseline should appear in the same batch as the failing diagnostic whenever practical.

---

## 5. Stage 2 — generate the full plausible hypothesis set

Before modifying code, enumerate the materially plausible explanations.

A hypothesis register should include, when relevant:

- runtime / executable mismatch;
- wrong subsystem or coupling edge;
- missing residual participation;
- sign / normal / orientation error;
- old/current state mismatch;
- AD derivative disconnect;
- active-set / branch degeneracy;
- premature nonlinear convergence;
- residual-floor / tolerance issue;
- functor caching or stale evaluation;
- boundary FaceArg / gradient reconstruction issue;
- timestep/discretization sensitivity;
- actual physics/formulation error.

Do not require every hypothesis to be equally likely. Assign a qualitative prior if useful:

```text
High / Medium / Low
```

but do not discard low-cost hypotheses solely because they look unlikely.

### Hypothesis-register template

| ID | Hypothesis | Prior | What observation would support it? | What observation would reject it? |
|---|---|---|---|---|
| H1 | ... | High | ... | ... |
| H2 | ... | Medium | ... | ... |

The register exists to prevent tunnel vision and to make the test batch intentional.

---

## 6. Stage 3 — build a discriminating test matrix

Design tests by asking:

> **Which cheap test distinguishes the largest number of currently plausible hypotheses?**

Map tests to hypotheses before execution.

Example:

| Test | bulk failure | wall failure | active-set | state mismatch | premature convergence | residual omission |
|---|---:|---:|---:|---:|---:|---:|
| bulk exact vs zero | High | — | — | Low | Medium | — |
| wall exact vs zero | — | High | Medium | Medium | Medium | Medium |
| smooth gate | — | Medium | High | — | Low | — |
| `nl_forced_its=2` | — | Low | Low | Low | High | Medium |
| tight `nl_rel_tol` | — | — | — | — | High | Medium |
| flux-vs-inventory identity | — | Medium | — | — | Medium | High |
| IC-amplitude sweep | — | Medium | Medium | Medium | High | Low |

The table is not a probability model. It is a **coverage map** showing which hypotheses each test can discriminate.

### Test-priority rule

Prefer tests with:

1. high hypothesis coverage;
2. low runtime / implementation cost;
3. independent failure signatures;
4. direct measurement of an invariant;
5. minimal source modification.

A test such as `forced2` is high value because it is cheap and can separate convergence failure from several apparent physics/coupling failures.

---

## 7. Stage 4 — batch execution and result signatures

Run the first discriminating set as one batch whenever practical.

The batch should normally contain:

- a known-good control;
- the minimal failing case;
- orthogonal subsystem cases;
- one or more convergence sensitivity cases for coupled nonlinear problems;
- any very cheap sign/state/branch discriminators;
- numeric invariant reporting.

Do not return only PASS/FAIL. Preserve a numeric result vector.

Example:

```text
R = {
  bulk_exact: PASS,
  bulk_zero: PASS,
  wall_exact: PASS,
  wall_zero: FAIL,
  forced2: PASS,
  tight_reltol: PASS,
  smooth_gate: FAIL,
  mass_balance_error: ...,
  wall_flux: ...
}
```

This **result signature** is the main diagnostic object. Compare it against the predicted signatures of the hypothesis set.

### Batch target

Aim to resolve most incidents in:

```text
Round 1: broad high-information diagnostic batch
Round 2: targeted confirmation batch, only if needed
```

A third round should usually mean either:

- the original hypothesis set was incomplete;
- the first-round tests had weak discriminatory power;
- more than one mechanism is interacting;
- source/framework instrumentation is now justified.

---

## 8. Orthogonal subsystem localization

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

Orthogonal localization should usually be part of the first batch, not a separate conversation round.

---

## 9. Conservation and residual accounting before source inspection

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

If the final diagnostic flux exists but the inventory update does not contain it, first include **residual participation and convergence** in the hypothesis set before changing the physical coefficient.

---

## 10. Mandatory convergence triage for coupled nonlinear problems

For coupled problems, include convergence sensitivity in the first diagnostic batch whenever any of these are true:

- one subsystem has a much larger initial residual than another;
- the solver reports convergence while a smaller subsystem violates an invariant;
- the final dominant field is correct but another coupled variable has a first-step balance error;
- exact initial conditions pass while approximate/zero initial conditions fail.

Run:

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
| all variants fail identically | move residual participation, discretization, or source-level hypotheses upward |
| forced extra iterations introduce a new solver failure | classify that failure separately; do not erase earlier successful invariant recovery |

### Generalized lesson from M5 wall migration

A large electrostatic residual can dominate the global nonlinear norm and allow relative convergence before a smaller species equation has completed its coupled Newton correction.

Therefore:

> If the converged dominant field is correct but a secondary physics invariant is wrong, test subsystem-sensitive convergence before changing physics.

---

## 11. Parameter sweeps and analytic signatures

When several hypotheses survive the first batch, sweep one control parameter while keeping all other quantities fixed.

Good sweep variables include:

- initial-condition amplitude;
- coupling strength;
- timestep;
- mesh spacing;
- mobility/conductivity scaling;
- boundary-field magnitude.

### Requirements

1. Define expected qualitative/quantitative patterns before running the sweep.
2. Change only one independent variable per sweep axis.
3. Preserve raw values, not just classification labels.
4. If possible, derive a reduced analytic model.

A distinctive analytic signature is often more powerful than additional source inspection.

### Example lesson

The M5 wall-migration initial-potential sweep produced values exactly matching a single Newton linearization of the bilinear wall term. That signature exposed premature nonlinear termination and was then independently confirmed by `forced2` and tight-relative-tolerance tests.

The combination of **analytic signature + independent recovery perturbations** is high-grade root-cause evidence.

---

## 12. Framework/source investigation only after black-box discrimination

Inspect framework internals when the test signature cannot distinguish the remaining hypotheses or when a targeted code question is now clear.

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
Result signature rejects bulk drift and active-set-only failure but supports convergence sensitivity.
Question: which convergence criterion accepts the first Newton state?
Inspect only the convergence path needed to answer that question.
```

---

## 13. Production fix selection

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

## 14. Evidence hierarchy

Use the strongest available evidence first.

From strongest to weakest:

1. analytic identity matched by measured output;
2. independent perturbations producing the same recovery;
3. orthogonal controlled experiment;
4. conservation/invariant accounting;
5. framework contract confirmed in source;
6. circumstantial symptom correlation;
7. intuition based only on code appearance.

Do not promote a hypothesis to root cause on code appearance alone.

### Root-cause confidence rule

Prefer at least two independent forms of evidence before declaring a root cause, for example:

```text
analytic signature
+ forced2 recovery
+ tight-relative-tolerance recovery
```

Multiple observations that all depend on the same mechanism are useful, but independent perturbations are stronger.

---

## 15. Diagnostic design templates

### 15.1 Hypothesis register

```text
Symptom:
    What is wrong?

Invariant:
    What must remain true?

Hypotheses:
    H1 ...
    H2 ...
    H3 ...

Known-good controls:
    ...
```

### 15.2 Test-matrix entry

```text
Test ID:
    T1

Perturbation:
    What one independent control changes?

Hypotheses discriminated:
    H1, H3, H5

Measured quantities:
    Which numeric outputs distinguish the hypotheses?

Predicted signatures:
    outcome A -> reject/support ...
    outcome B -> reject/support ...
```

### 15.3 Batch result

```text
Batch ID:
    B1

Result vector:
    T1 -> ...
    T2 -> ...
    T3 -> ...

Rejected hypotheses:
    ...

Surviving hypotheses ranked:
    ...

Need second batch?
    yes/no
```

Predicted signatures should be written before execution whenever practical. Otherwise post-hoc interpretation can drift toward whichever hypothesis currently looks attractive.

---

## 16. Incident-to-guide promotion rule

Incident logs preserve history. This guide preserves reusable knowledge.

At incident closure:

1. keep the full chronological evidence in the incident log;
2. record the original hypothesis set and diagnostic batches;
3. extract only generalized, reusable rules;
4. add or refine those rules in this guide;
5. remove incident-specific variable names unless useful as examples;
6. link back to the incident when provenance matters;
7. add or promote a canonical regression for the fixed invariant.

Also preserve useful **symptom-to-batch mappings** such as:

```text
Symptom pattern:
    final dominant field correct
    + secondary conservation wrong
    + exact IC pass
    + zero/approximate IC fail

Recommended first batch:
    subsystem localization
    + default convergence
    + forced2
    + tight relative tolerance
    + invariant accounting
```

Over time these mappings form a MOOSE diagnostic decision system rather than a collection of isolated lessons.

---

## 17. Update policy

This document is a living protocol.

Update it when one of the following occurs:

- a diagnostic batch proves substantially faster than the current recommended set;
- a repeated failure signature appears in more than one incident;
- a previously recommended test produces misleading conclusions;
- a new MOOSE-native mechanism improves convergence/debugging;
- an incident invalidates an existing rule;
- a new invariant becomes important enough to standardize;
- a new high-information test can replace several sequential tests.

Every update should state:

```text
What changed?
Why?
Which incident/evidence motivated it?
Does it replace or refine an existing rule?
```

Prefer refinement over accumulating contradictory rules.

---

## 18. Fast path checklist

For a new coupled MOOSE regression, use this workflow by default:

```text
[ ] 1. Confirm solver/runtime actually reaches physics
[ ] 2. Identify known-good canonical baseline and governing invariant
[ ] 3. Generate the plausible hypothesis set up front
[ ] 4. Build a hypothesis-to-test coverage matrix
[ ] 5. Select the smallest high-information first batch
[ ] 6. Include orthogonal subsystem localization where relevant
[ ] 7. Include invariant/conservation accounting
[ ] 8. Include default vs forced2 vs tight-relative-tolerance for coupled nonlinear symptoms
[ ] 9. Execute the batch and preserve the full numeric result signature
[ ] 10. Reject/rank hypotheses from the signature
[ ] 11. If needed, run one targeted confirmation batch or analytic sweep
[ ] 12. Only then inspect framework/source internals
[ ] 13. Validate production fix against canonical + incident regression
[ ] 14. Promote reusable symptom/signature/batch knowledge into this guide
```

### Round-count objective

```text
Most incidents: 1 broad batch + at most 1 targeted batch
```

Do not create extra conversation/test rounds when several independent discriminators can safely be packaged together.

---

## 19. Current reusable rules

### 19.1 Parallel-hypothesis rule

Generate the plausible hypothesis set before the first diagnostic batch. Avoid serial tunnel vision around the first plausible code-level explanation.

### 19.2 Information-gain rule

Prioritize tests by how many plausible hypotheses they can distinguish per unit cost.

### 19.3 Batch-parallel / test-controlled rule

Run many controlled diagnostics together, but keep each individual case to one independent perturbation whenever possible.

### 19.4 Result-signature rule

Treat the vector of numeric outcomes across a test batch as the primary diagnostic evidence, not isolated PASS/FAIL labels.

### 19.5 Residual-floor rule

Before tightening an absolute nonlinear tolerance, measure the numerical residual floor. A tolerance below the floor can produce false line-search/divergence incidents even when the algebraic state is already converged.

### 19.6 Convergence-triage rule

When the final dominant field is correct but a secondary coupled invariant is wrong, include `default / forced2 / tight relative tolerance` in the first diagnostic batch before changing physics.

### 19.7 Invariant-over-return-code rule

A solver return code does not determine physical correctness. Always compare the invariant itself.

### 19.8 Healthy-subsystem exclusion rule

Once an orthogonal matrix clears a subsystem, stop modifying it unless new evidence reopens it.

### 19.9 Analytic-signature rule

If a reduced analytic model predicts a distinctive numeric pattern and the sweep matches it, treat that as high-grade root-cause evidence.

### 19.10 Two-round target rule

Design diagnostics so that most incidents can be solved in one broad batch and, if required, one targeted confirmation batch.
