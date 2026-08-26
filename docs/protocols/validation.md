# Validation Protocol

**Status:** canonical procedure  
**Scope:** MOOSE/QPX executable batches, checkers, production parity, and imported-data validation  
**Purpose:** catch construction and checker defects before user runtime and produce causally interpretable evidence.

## VAL-01 — Mandatory P0-P3 order

```text
P0 checker/analyzer self-test and mutation controls
P1 static construction/input checks
P2 qpx-opt --check-input
P3 full runtime / physics validation
```

P0-P2 failures are construction/harness/infrastructure evidence, never physics FAIL.

## VAL-02 — Validator sufficiency audit before delivery

Before an external batch is accepted, answer:

```text
What exact claim will PASS establish?
Which failure classes are covered?
Which plausible classes remain uncovered?
Can implementation and checker share the same bug?
Is the actual production path exercised?
Are negative controls/mutations present?
Are construction failures separated from physics failures?
Are acceptance thresholds predeclared?
```

Use explicit decisions such as:

```text
TEST_SET_INSUFFICIENT
STATIC_PIPELINE_PASS_ONLY
PRODUCTION_PATH_UNVALIDATED
VALIDATOR_SELFTEST_UNVALIDATED
BATCH_ACCEPTED_FOR_EXECUTION
```

## VAL-03 — Static construction defenses

Apply relevant checks before `qpx-opt`:

```text
duplicate blocks/objects
reserved parser symbols (including x,y,z,t where applicable)
unused top-level substitutions
missing referenced files
missing expected outputs/postprocessors
missing functor providers
generated dot-functor naming
variable/material property naming consistency
unknown/duplicate species and aliases
invalid/colliding canonical pair keys
unsupported input parameters
stale previous outputs
unresolved template markers
```

If property `X_state` is created with `define_dot_functors = true`, the generated derivative functor is `dX_state_dt`. Example: `w_O_state -> dw_O_state_dt`.

## VAL-04 — Analyzer/checker is part of the system under test

A checker is trusted only after controlled self-tests.

Required behavior when applicable:

```text
positive control -> accepted
negative/mutated control -> rejected
construction failure -> not labeled physics failure
runtime success + metric failure -> exact failed metric reported
initialization-only rows -> excluded or explicitly classified when non-physical
supporting diagnostic -> must not override direct target PASS unless contract allows it
```

## VAL-05 — Predictive branch-aware batching

For each test declare:

```text
Test ID
Hypothesis
input/reference revision
independent control changed
measured quantities
predicted structural/numeric signature
PASS rule
FAIL class
immediate fail-branch tests
```

Include cheap fail-branch discriminators in the same external bundle when they remain interpretable after the primary failure. Do not count prerequisite-dependent descendants as independent evidence.

## VAL-06 — Known-good and environment identity

When available, package the exact historical known-good control in the same round as the candidate. Record enough executable/build identity to interpret simultaneous control failure, including executable `realpath`; add version/SHA/linkage evidence when the incident makes it relevant.

A runner must resolve the supplied executable with `realpath` before `cd` or relative-path changes.

## VAL-07 — Runtime result signature

Do not report only PASS/FAIL. Preserve the numeric/structural result vector needed to discriminate hypotheses, such as residuals, conservation errors, fluxes, inventory changes, positivity minima, reference errors, selected provenance, or branch identity.

## VAL-08 — Production-path parity

Static/reference agreement is insufficient when the real QPX parser/resolver/material/solver path could differ. Canonical promotion requires representative production-path execution against an independent reference or invariant where applicable.

## VAL-09 — Artifact packaging

Standalone user-run bundles should contain execution and analyzer artifacts needed for the test. Do not add README, decision documents, incident documents, `.gitignore`, or unrelated executables unless explicitly requested.

The bundle should make one external execution round sufficient to run P0-P3 and all predeclared cheap branches whenever practical.

## VAL-10 — Imported data validation order

For transport/thermo/chemistry/imported data, validate one layer at a time:

```text
source data
-> raw extraction parity
-> metadata/provenance
-> model-state dependency inventory
-> representation adequacy
-> canonical key/alias resolution
-> unit conversion
-> interpolation/range policy
-> derived coefficients
-> production-path parity
-> coupled integration
```

A downstream failure must not be interpreted as physics evidence until prerequisites pass.

## VAL-11 — Resolver invariants

For pair databases with aliases/fallbacks, require:

```text
resolve(a,b) == resolve(b,a)
identity resolution is deterministic
explicit data > fallback
charged identity is never silently neutralized
excited-state collapse affects only the declared excitation dimension
every physical pair resolves to explicit data or an explicitly named fallback
selected provenance is observable
```

## VAL-12 — Canonical A0-A7 data-pipeline template

Use the following stages for imported transport-style data when applicable.

### A0 — schema/static preflight
Check unique identifiers, alias targets, charge preservation, canonical pair keys, grid ordering, finite values, malformed/duplicate entries.

### A1 — source/provenance parity
Compare all required explicit source pairs against a pinned source revision, including pair orientation, grid, units, metadata, references, and completeness.

### A2 — raw-to-runtime transformation parity
Validate conversion across the full table when practical. Distinguish missing factors, double conversion, wrong units, sign/indexing/orientation defects.

### A3 — exhaustive resolver
Enumerate ordered physical-species queries and verify expected canonical unordered-pair resolution, precedence, symmetry, charge preservation, and excitation collapse.

### A4 — interpolation/range parity
Check exact grid points, off-grid points, boundaries, boundary ±epsilon, clipping/extrapolation behavior. Do not impose monotonicity unless the source/model requires it.

### A5 — provenance/precedence trace
Required explicit pairs must report explicit provenance; true missing pairs must report the declared fallback; fallbacks must not shadow explicit data.

### A6 — production-path end-to-end parity
Exercise representative explicit, alias-to-explicit, ion-neutral fallback, and charged-charged fallback cases through the real QPX path and compare with an independent reference.

### A7 — validator mutation self-test
Inject controlled defects such as charge collapse, removed explicit pair, unit-factor deletion, precedence inversion, interpolation change, duplicate alias, or missing functor. The intended gate must detect each mutation.

Canonical data-pipeline acceptance requires A0-A7 PASS unless the work item explicitly defines a narrower justified scope.

## VAL-13 — Decision classes

Prefer specific classes over generic FAIL, including:

```text
HARNESS_OR_CONSTRUCTION_FAIL
MISSING_FUNCTOR_FAIL
SOURCE_PARITY_FAIL
METADATA_FAIL
UNIT_TRANSFORM_FAIL
RESOLVER_FAIL
INTERPOLATION_FAIL
PRECEDENCE_FAIL
REPRESENTATION_ADEQUACY_FAIL
PRODUCTION_PATH_PARITY_FAIL
VALIDATOR_SELFTEST_FAIL
SOLVER_CONVERGENCE_FAIL
PHYSICS_MODEL_FAIL
BATCH_PASS
```

## VAL-14 — Promotion rule

A diagnostic workaround is not canonical merely because it recovers a result. Promotion requires the intended production mechanism plus representative regression coverage, invariants, and checker sensitivity.

When a failure class recurs or proves broadly reusable, add the check to this protocol or `docs/knowledge/TROUBLESHOOTING_INDEX.md`; do not duplicate the rule in issue bodies.

## VAL-15 — Observation-path audit for derived runtime quantities

Before accepting a checker that consumes a derived transient quantity, document its observation path end to end:

```text
measured physical quantity
-> production owner / nonlinear variable or material functor
-> current/old state semantics
-> producer execute stage
-> intermediate Aux/functor stages, if any
-> consumer execute stage
-> postprocessor/output aggregation
-> checker interpretation
```

The Validator must answer:

```text
Does every consumer see the intended timestep/state?
Is any same-stage producer/consumer ordering assumed without a framework guarantee?
Can an Aux copy become one timestep stale?
Can a timestep-end output copy be mistaken for a variable with a framework-owned derivative?
Does the checker observe production state directly when a simpler path exists?
```

Prefer the shortest observation path that preserves the production quantity. Avoid same-stage Aux-to-derived-Aux dependencies unless execution ordering is explicitly guaranteed and covered by a semantic test.

## VAL-16 — Continuous versus discrete identity classification

Every temporal or nonlinear consistency gate must be classified before it is used for PASS/FAIL:

```text
CONTINUOUS_IDENTITY
DISCRETE_EXACT_IDENTITY
TIME_INTEGRATOR_SPECIFIC_IDENTITY
DIAGNOSTIC_APPROXIMATION
```

Only an identity proven exact for the discrete state and chosen time integrator may be used as a strict finite-timestep equality gate.

In particular, for a nonlinear transformation `G(S)`, do not assume

```text
(G(S_n)-G(S_{n-1}))/dt == G'(S_n) * (S_n-S_{n-1})/dt
```

at finite `dt` unless that equality is derived for the actual discretization. A continuous chain rule may remain a valid model identity while the corresponding nonlinear backward secant differs by `O(dt)`.

When an exact linear state exists, validate temporal parity on that state and report nonlinear transformed-state secants as diagnostics unless an exact discrete formula is available.

## VAL-17 — Temporal semantic self-test

Transient checkers must test timestep semantics, not only static formula mutations.

When applicable, P0 must include a small synthetic multi-step sequence that distinguishes at least:

```text
correct same-step derivative/value        -> PASS
one-step shifted/stale derivative/value   -> FAIL
correct magnitude with wrong sign         -> FAIL
correct sign with wrong magnitude         -> FAIL
initialization-only/non-physical rows      -> excluded or explicitly classified
```

If the checker combines direct time derivatives with derived functors, add a mutation or synthetic sequence that reproduces a one-timestep lag. A checker that cannot reject the shifted sequence is `VALIDATOR_SELFTEST_UNVALIDATED` and must not be sent for external P3 execution.

Temporal semantic self-tests complement source/static mutations; one does not substitute for the other.