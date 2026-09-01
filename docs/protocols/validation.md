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
duplicate functor/material-property producers by block
generated dot-functor naming
variable/material property naming consistency
unknown/duplicate species and aliases
invalid/colliding canonical pair keys
unsupported input parameters
stale previous outputs
unresolved template markers
```

For generated overlay/integration inputs, P0 must build a block-qualified provider ownership map for referenced shared properties:

```text
(property_or_functor_name, block) -> intended producer set
```

A referenced property with no applicable producer is a hard construction failure. Multiple unintended producers for the same property on the same applicable block are also a hard construction failure and should be classified `DUPLICATE_PROVIDER_FAIL`. Prefer reusing the already-owned upstream provider for shared state such as gas temperature, pressure, density, or common mesh/material properties rather than recursively copying a second provider subgraph. When this failure class is in scope, include a negative mutation that deliberately duplicates one shared provider and prove P0 rejects it before P2.

For `ParsedFunctorMaterial` / `ADParsedFunctorMaterial`, reserved-symbol validation is a **hard machine-enforced P0 gate**, not a manual-review item. Every generated or packaged input containing these objects must run `python3 bin/qpx.py preflight <input.i>` or an equivalent embedded guard before P2. See VAL-19.

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
DUPLICATE_PROVIDER_FAIL
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

## VAL-15 — Observation-path audit for derived/transient quantities

Before an external transient batch uses a derived observable as an acceptance gate, document its observation graph:

```text
production state owner
-> current/old state semantics
-> derivative/provider stage
-> derived functor/material stage
-> Aux/postprocessor consumer stage
-> output/checker stage
```

The Validator must confirm that the consumer observes the intended timestep/state and that no same-stage ordering dependency can silently produce stale values.

Prefer direct production-state or postprocessor evaluation over multi-hop Aux copies when both are available.

## VAL-16 — Semantic identity and equivalence classification

Before any acceptance comparison, classify both the **semantic objects** being compared and the **equivalence relation** required by the claim. A validator must not assume that two representations are interchangeable merely because they are numerically close, textually similar, derived from the same source, or produced in the same run.

Use the narrowest applicable class, for example:

```text
syntax / byte exact
identifier / enum exact
continuous analytic identity
discrete exact identity
time-integrator-specific exact identity
representation-equivalent numeric
numerical tolerance
diagnostic approximation / convergence / refinement
physical-model tolerance
```

The comparison relation must satisfy both sides of the CORE-16 contract:

```text
not stronger than the producing representation guarantees
not weaker than the scientific claim requires
```

Hard rules:

1. Use exact equality only when exact identity is guaranteed by the representation and required by the claim.
2. Decimal serialization, floating-point arithmetic, formatting, and reparsing normally require a narrowly justified representation-level numeric comparison rather than bit/exact equality. Mutation-test that a materially different value still fails.
3. Static source classifiers must validate semantic capability rather than one exact token sequence unless the exact syntax itself is the invariant.
4. Integral/average identities must compare compatible aggregation operators over the same domain and weighting; extrema or other summaries are not substitutes for a domain average unless the mathematics proves equivalence.
5. Source/provenance validation and production-parity validation must keep their numerical convention/provenance contracts explicit; do not silently treat historical source constants and host-production constants as the same object.
6. State/time identity is part of equivalence. An INITIAL observation, stale/old state, timestep-end state, and converged nonlinear state are distinct unless the observation contract proves otherwise; see VAL-15, VAL-17, and VAL-20.
7. A supporting proxy diagnostic must not override a passing direct target merely because the proxy uses a different representation or environment; see VAL-04.

For temporal/numerical identities in particular, only a relation exact for the actual discrete scheme may be used as a zero/tight-tolerance exact PASS gate. Do not require exact equality between a nonlinear continuous derivative and a finite-step secant unless the discrete algebra proves that equality. Use non-exact continuous/secant comparisons only as diagnostics or refinement studies.

If a checker fails because it demanded an unjustified equivalence relation, classify the event as `VALIDATOR_SELFTEST_FAIL` or a narrower validation/contract failure, not a physics failure. Preserve a negative control that proves the corrected equivalence does not hide a material defect.

## VAL-17 — Temporal semantic self-test

Transient checkers and observation paths require synthetic temporal self-tests when timestep alignment matters.

At minimum, test a short deterministic sequence that distinguishes:

```text
correct same-step quantity -> PASS
one-timestep shifted/stale quantity -> FAIL
wrong sign -> FAIL
wrong magnitude beyond tolerance -> FAIL
```

When the output stream can contain an `INITIAL` / start-time row, the checker must also carry an explicit initialization-row mutation:

```text
initialization-only row deliberately inconsistent with the physical invariant
-> checker excludes or explicitly classifies that row
-> solved timestep rows remain fully enforced
```

A transient checker that silently applies a physical timestep invariant to an initialization-only observation row is `VALIDATOR_SELFTEST_FAIL`, not a physics failure. This initialization-row branch is mandatory after any prior incident involving `time=0`, initialization order, output-stage timing, or pre-solve postprocessor values.

When a prior failure involved initialization order, Aux execution stage, old/current state, or derivative timing, include the corresponding semantic mutation in P0 before another external execution.

## VAL-18 — Runtime environment/JIT preflight

When QPX/MOOSE input construction depends on runtime/JIT facilities, P1/P2 preparation must verify the required project environment before classifying parser/JIT failures as input defects.

For environment-sensitive cases, record:

```text
activation environment / expected conda environment
qpx-opt realpath
relevant JIT/runtime dependency availability
```

A symptom such as `ADFParser::JITCompile() failed` at P2 is initially `ENVIRONMENT_OR_BUILD_FAIL` versus `HARNESS_OR_CONSTRUCTION_FAIL`; compare against the known-good activation state before editing the accepted input. A successful rerun under the correct environment without input changes supports environment attribution.

## VAL-19 — Parsed-function namespace preflight

Any test, diagnostic, standalone input, or canonical regression that contains `ParsedFunctorMaterial` or `ADParsedFunctorMaterial` must pass a parser-namespace static preflight before `qpx-opt --check-input`.

MOOSE `ParsedFunctorMaterial` appends coordinate/time parser variables `x,y,z,t` and registers constants `pi,e`. Therefore user-provided parser aliases must not collide with those names.

Hard P0 checks:

```text
custom functor_symbols do not contain x,y,z,t,pi,e
implicit parser symbols from functor_names are checked when functor_symbols is omitted
no duplicate parser symbols inside one parsed object
parser symbols are valid identifiers
```

Canonical implementation:

```text
python3 bin/qpx.py preflight --self-test
python3 bin/qpx.py preflight <generated-or-packaged-input.i>
```

For external overlay bundles that do not carry the repository `bin/` entrypoint, the case `prepare.py` must embed or invoke an equivalent guard. A bundle containing parsed functor objects is not `BATCH_ACCEPTED_FOR_EXECUTION` until this gate passes.

Preferred generated aliases are semantic multi-character names such as `fp_rho`, `fp_w`, `meanM`, or `pres`; avoid single-letter aliases unless they are explicitly known not to collide with the parser namespace.

The signatures

```text
Syntax error in parameter 'Vars' given to FunctionParser::Parse()
Invalid function <expression>
```

are first classified as `HARNESS_OR_CONSTRUCTION_FAIL`. Inspect parser-symbol declarations before changing physics, solver tolerances, transport data, or timestep.

## VAL-20 — Runner-owned temporal CSV semantics

Transient CSV row classification is a runner responsibility, not a repeated case-checker responsibility.

All new or modified transient cases with a checker must declare `validation_schema = 2` in `test.json`. If the checker consumes transient CSV data, the manifest must declare either a `temporal_csv` normalization contract or an explicit raw-row policy.

When the `INITIAL` / start-time row is observation-only, declare separate raw and physical CSVs:

```json
{
  "validation_schema": 2,
  "checker_args": ["--csv", "input_out.physical.csv"],
  "temporal_csv": [
    {
      "source": "input_out.csv",
      "physical": "input_out.physical.csv",
      "time_column": "time",
      "initial_row_policy": "exclude_observation",
      "initial_time": 0.0,
      "time_tol": 1e-15
    }
  ]
}
```

Canonical command-line implementation is `python3 bin/qpx.py temporal-csv ...`; the reusable implementation is `qpx_harness.temporal`. The runner normalizes the raw CSV after P3 and before the case checker. Raw runtime evidence is preserved unchanged.

Hard schema-v2 rules:

```text
no silent first-row dropping inside case checkers
no checker reference to raw CSV when initial_row_policy=exclude_observation
source and physical CSV paths must differ
non-monotone/non-finite time values fail normalization
at least one physical row must remain unless explicitly waived
```

If the start-time row is physically part of the acceptance contract, declare:

```text
temporal_csv_policy = include_initial_as_physics
```

If the transient checker does not consume temporal CSV data, declare:

```text
temporal_csv_policy = not_applicable_no_temporal_csv
```

Legacy schema-v1 regressions are grandfathered until modified. Any new or touched transient case must migrate to schema v2. This prevents recurring false negatives where a pre-solve `t=0` observation row is treated as a solved physical timestep.

## VAL-21 — Numerical contract preflight and runtime semantic gate

Use this rule when a generated or bounded executable case depends on numerical scales or control semantics that can conflict with framework defaults, adaptive controls, coupling cadence, sync behavior, or the experiment's declared physical/numerical regime.

Keep the canonical `P0 -> P1 -> P2 -> P3` order from VAL-01. This rule adds two sub-gates:

```text
P1 numerical-contract gate
P3 runtime-semantic gate -> physics checker
```

### P1 numerical-contract gate

Before P2, declare the experiment intent when numerical scale matters, for example:

```text
transient-resolution
fixed-step discriminator
adaptive transient
subcycled fast solve
quasi-steady relaxation
periodic/frequency-domain reduction
steady solve
```

Construct an **effective numerical contract**, not merely a list of parameters written in the input. Include the applicable requested and framework-effective controls, such as:

```text
start_time / end_time
dt / dtmin / dtmax / num_steps
timestep_tolerance
TimeStepper/adaptivity controls
abort/cutback behavior
sync/output times
MultiApp/subcycle dt ownership
nonlinear/linear solve controls when they determine the experiment semantics
```

Prefer executable-derived framework truth from the actual user-local `qpx-opt` when practical. MOOSE applications expose registered input syntax and defaults through syntax dumps such as `--yaml` / `--json`, while `--show-input` exposes the parsed input after input processing/overrides. If executable introspection cannot provide the required effective value, use pinned framework/QPX source or versioned documentation and record that fallback identity. Do not silently hardcode a framework default into a reusable runner without an identity/provenance contract.

Reject hard contradictions before P2. Applicable examples include:

```text
requested fixed dt below an effective dtmin
final-time interval indistinguishable from framework timestep/sync tolerance
requested physical step/output count impossible under start/end/dt controls
fixed-step discriminator permitting silent timestep cutback or adaptivity
sync/output cadence unable to emit the required physical observations
MultiApp/subcycle ownership inconsistent with the declared coupling cadence
```

Do not invent universal numerical-accuracy thresholds in this validation rule. When the experiment depends on a physical/model scale such as `dt/tau`, `h/lambda`, Knudsen number, diffusive/drift ratio, RF period, or coupling timescale, obtain the scale definition and acceptance meaning from the owning source/model/coupling contract (for coupled architecture see PS-23). VAL-21 verifies that the requested numerical configuration is consistent with that declared intent; it does not redefine the physics criterion.

A P1 contradiction is construction evidence, not physics evidence. Classify it as:

```text
HARNESS_OR_CONSTRUCTION_FAIL / NUMERICAL_CONTRACT_FAIL
```

and do not spend a P3 external round merely to discover the same contradiction at runtime.

### P3 runtime-semantic gate

A process return code of zero is not enough to begin physics validation. Before the physics checker consumes results, verify that the runtime actually executed the numerical experiment that was declared at P1.

Check the applicable semantics, for example:

```text
minimum required physical timestep/output rows exist
actual first/final physical time is compatible with the requested interval
actual step count/cadence is compatible with the declared fixed/adaptive/subcycle mode
fixed-step discriminators did not silently cut back or change dt
required branch/coupling mode actually executed
required outputs exist and represent solved physical states rather than only INITIAL state
```

Preserve raw logs/output even when this gate fails. A runner/analyzer must convert missing or inconsistent temporal/runtime semantics into a structured result; it must not erase the external batch with an uncaught checker/analyzer exception.

A runtime-semantic failure precedes physics interpretation. Classify it as:

```text
HARNESS_OR_CONSTRUCTION_FAIL / RUNTIME_SEMANTIC_FAIL
```

unless a narrower infrastructure class is already established.

### Validator self-tests

When this rule is material to the batch, include cheap controlled mutations for the relevant contract edges. Examples:

```text
framework default conflicts with requested microstep
end_time/timestep_tolerance suppresses all physical steps
num_steps/end_time/dt are inconsistent
fixed-step intent permits unintended cutback/adaptivity
runtime contains INITIAL row only
runtime final time or physical-row count misses the declared contract
```

The negative mutation must fail at P1 or the P3 runtime-semantic gate, not later as a physics failure.

### Reusable implementation direction

Prefer a shared machine-readable numerical-contract report over case-specific `if` statements. A reusable report should distinguish:

```text
requested controls
framework-effective controls and provenance
derived model/scale inputs supplied by the owning contract
declared experiment intent
hard contradictions
expected runtime semantics
observed runtime semantics
terminal validation class
```

This layer is intended to generalize across electron/Poisson microsteps, chemistry stiffness, Maxwell period handling, heavy-transport scale audits, MultiApp subcycling, and other multiphysics cases without forcing all physics into one timestep or duplicating the scale definitions owned elsewhere.
