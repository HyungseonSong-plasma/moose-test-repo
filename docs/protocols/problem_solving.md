# Problem-Solving Protocol

**Status:** canonical procedure  
**Scope:** MOOSE/Physics technical issues and bounded child work items  
**Purpose:** front-load high-value research, framing, and discrimination so external runtime execution is informative and avoidable repetition is reduced.

## PS-01 — Phase 0 problem framing

Before external runtime execution, define:

```text
Closure claim
Known-good control
Primary unknown classes
Dependency graph
Research questions
Expected evidence/signatures
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

## PS-07 — External execution sequence

When runtime execution is required, prefer an information-rich sequence rather than repeated ad-hoc runs:

```text
broad discrimination
  -> targeted confirmation / fix validation when needed
  -> canonical production regression when the claim is ready to close
```

The sequence is not a numeric budget and is not scored.

Broad discrimination should combine applicable P0-P3 checks, a known-good control, candidate, independent reference/oracle, predeclared failure branches, and environment/executable identity.

After one dominant failure class is established, change only that class unless new evidence falsifies the diagnosis. Do not stack speculative changes across physics, solver, parser, and environment.

The final production regression should exercise the canonical path, representative regime, relevant boundary/edge cases, physical/analytic invariants, known-good non-regression, and negative controls.

If closure regression fails, return to diagnosis, split a newly independent failure class, or redefine the claim rather than treating another external run as automatic progress.

## PS-08 — Coupled nonlinear convergence triage

For coupled problems, include convergence sensitivity in the initial discrimination batch whenever a dominant subsystem can hide a smaller one, exact IC passes while zero/approximate IC fails, or a physical invariant is wrong despite solver convergence.

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

Minimize avoidable external execution and assistant-caused rework while preserving or improving closure quality.

Do not maintain EVR/DBR/RWR/RVR counters as a Paul operating metric. Use current evidence to decide whether another run adds independent information or whether the plan should be redesigned.

## PS-15 — Issue sizing and decomposition

Execution issues should be small enough that one bounded closure claim has a coherent diagnosis, implementation, and validation path.

Preferred execution boundary:

```text
1 closure claim
1 bounded subsystem or coupling edge
ideally 1 production decision
clear rollback / acceptance boundary
```

Treat broad architecture/planning items primarily as parents. Decompose when they contain multiple serial closure claims, separable source/model uncertainty and runtime integration, independent coupling edges, or stages that can close independently.

Do not keep a large parent open merely to aggregate operating-process statistics. A parent may close as `DECOMPOSED_PARENT` after validated history and successor links are recorded; that does not claim downstream physics is complete.

## PS-16 — Test IDs and execution batches are distinct

Name internal cases/tests by the discriminator they own:

```text
T1 material exposure
T2 independent oracle
T3 coupling ON/OFF
T4 transient integration
```

A runtime batch may contain several such tests. Do not encode operating-round counters into test identity.

## PS-17 — No operating-round accounting

Paul does not increment EVR/RWR or similar interaction-efficiency counters.

After each attributable runtime result, update only the durable technical state that matters: established evidence, rejected hypotheses, unresolved class, next validation obligation, and any assistant-caused defect that needs correction.

## PS-18 — Repetition stop-and-redesign rule

Repeated avoidable external execution is a qualitative redesign signal, not a scored threshold.

Before asking for another run after an assistant-side artifact/config/checker defect or repeated nondiscriminating result, re-audit the observation graph, checker semantics, construction, and batch design. Continue only when the next run has a clear independent claim.

## PS-19 — Promotion-ready planning

Phase 0 must classify intended tests as either diagnostic-only or promotion candidates.

For each promotion candidate predeclare:

```text
canonical regression destination
production mechanism exercised
promotion condition
representative invariant/control
negative checker/mutation requirement
final regression membership
```

A successful diagnostic should be promotable without redesigning its physical test semantics. If substantial checker, timestep, mesh, solver, or physical-model changes are required only at promotion time, return to Validator review before canonicalization.

## PS-20 — Environment activation preflight

Before running a user-local Physics batch that depends on a project runtime environment, verify the environment contract explicitly rather than assuming the interactive shell is already prepared.

At minimum record or check the applicable activation state and executable identity before P2:

```text
required environment activated
physics-opt realpath matches the intended executable
critical runtime/JIT dependencies resolve in that environment
```

If a previously accepted case fails at P2 with an environment-sensitive symptom such as JIT compilation failure, first compare the activation/runtime identity with the known-good environment before changing input physics or harness logic.

## PS-21 — Performance-feasibility gate before closure-scale runtime

Before a production-like coupled P3 or closure-scale regression, estimate whether the proposed numerical architecture is practical enough to serve as a regression.

Record the applicable cost drivers before external execution:

```text
nonlinear unknown blocks / approximate DOF count
monolithic vs segregated coupling structure
linear solver / preconditioner
process/thread count
time-step count and case-matrix size
known-good subsystem wall times when available
new global elliptic or strongly coupled blocks added since the known-good path
```

When a new architecture adds a global coupling block or materially enlarges the nonlinear system, include a bounded cost discriminator before the final regression, such as:

```text
standalone new subsystem runtime
one physical timestep
one representative coupling axis
transport-only vs coupled wall-time comparison
```

If a representative first step is computationally impractical or the projected closure matrix is not regression-viable, classify the architecture before spending the closure-scale runtime:

```text
PERFORMANCE_FEASIBILITY_UNRESOLVED
PERFORMANCE_BOUND
ARCHITECTURE_UNSUITABLE_FOR_REGRESSION
```

Do not compensate by arbitrary tolerance, timestep, source-amplitude, boundary-condition, or physics tuning. Redesign, segregate, precondition, or decompose from evidence.

### Implementation granularity

For performance-sensitive MOOSE/Physics implementation, separate **physics granularity** from **computational granularity**:

```text
physics decomposition      = split by mathematical/physical responsibility
computational decomposition = split/share/fuse by measured execution cost
```

Logical modularity must not create computational duplication. In hot residual/Jacobian paths:

1. a consumer should evaluate only the dependency cone required for its requested output;
2. repeated expensive primitives may be shared when consumers use the same state, location, and execution frequency;
3. do not fuse objects merely to reduce object count, and do not split expensive evaluation merely for interface symmetry;
4. before changing granularity, measure or estimate call amplification, cost per call, duplicated work, and relevant AD dependency width;
5. performance-specialized paths must preserve the production physics contract and receive direct equivalence/non-regression validation before promotion.

The optimization target is not minimum object count. It is minimum repeated expensive work subject to physics clarity and validation parity.

## PS-22 — Live observability is part of long-run batch design

A runtime whose cost or convergence is uncertain must expose progress while it is running. Do not make process termination the first moment at which useful solver evidence becomes visible.

Required when applicable:

```text
CASE START / CASE END markers
stdout/stderr streamed live and written incrementally to a log
elapsed wall time
physical timestep / nonlinear iteration progress when the application exposes it
return code and final result path
```

Using `subprocess.PIPE` is acceptable only if output is consumed and surfaced continuously. Capturing all solver output silently until process exit is not acceptable for a potentially long P3.

If manual `/proc`, `ps`, CSV-row, I/O, or context-switch probes become necessary to determine whether a run is alive, the next artifact must promote the useful progress signals into runner-owned observability rather than repeating the same manual diagnosis.

## PS-23 — Coupling-architecture gate: performance and stability are joint requirements

A change between monolithic, segregated, staggered, explicit-lagged, fixed-point, or semi-implicit coupling is a numerical-model decision, not a pure performance refactor.

Before freezing the new architecture, inventory the feedback edges and the stability/convergence mechanisms they lose or gain. Check the relevant physical/numerical timescales and contraction conditions, for example:

```text
dielectric / Maxwell relaxation
advective CFL
diffusive timescale
reaction/chemistry timescale
fixed-point/Gummel contraction
lagged-field or lagged-source dependencies
```

Separate two claims:

```text
coupling closure: information reaches the intended downstream state
numerical stability: the chosen split/iteration remains stable and convergent for the intended timestep/regime
```

A short causal-response test may prove closure without proving stability. If a one-pass staggered method violates a source-backed timescale or is noncontractive, prefer a justified block-iterative/fixed-point or semi-implicit architecture rather than reducing the physical timestep merely to make the regression pass.

## PS-24 — Repetition-compression rule

Repeated manual work is evidence of a missing reusable discriminator or missing automation.

During a bounded work item, if the same diagnostic class is performed repeatedly, stop before adding another ad-hoc probe and ask:

```text
Can this evidence be emitted by the runner?
Can it be checked in P0/P1/P2?
Can a subsystem timing/control isolate it before full P3?
Can a source/API audit settle it before another external run?
```

Promote the answer into the next artifact or canonical protocol when reusable. Typical examples include:

```text
live process/progress status
wall-time accounting
CSV physical-row detection
provider/ownership inventory
subsystem cost isolation
coupling residual history
stability-timescale diagnostics
```

The objective is not to eliminate all iteration; it is to prevent the same uncertainty from being rediscovered manually in successive rounds.