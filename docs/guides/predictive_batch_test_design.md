# Predictive Batch Test Design

**Status:** living guide  
**Scope:** MOOSE/QPX research, verification, debugging, and data-validation workflows  
**Purpose:** reduce diagnostic round trips by predicting likely failure modes before execution and embedding the next discriminating tests into the same batch whenever practical.

## 1. Core principle

Do not design only the primary test. Before execution, assume that the primary test fails and ask what evidence will be needed next.

The default pattern is:

```text
hypothesis H
  -> primary discriminator T
       ├─ PASS -> predeclared pass-branch decision / next gate
       └─ FAIL -> predeclared fail-branch discriminator(s)
```

For a batch with several hypotheses:

```text
known-good invariant
  -> hypothesis set H
  -> primary discriminators T
  -> failure pre-mortem
  -> cheap branch tests added to the same batch
  -> construction preflight
  -> execution
  -> result signature
  -> immediate hypothesis decision
```

The optimization objective is not to maximize test count. It is to maximize information obtained per external execution round while keeping every test causally interpretable.

## 2. Predictive pre-mortem before execution

Before packaging a batch, list plausible ways each primary test can fail. At minimum separate:

1. **Harness / construction failure** — malformed input, duplicate block, missing output, parser collision, wrong executable path, missing functor/provider.
2. **Reference-data failure** — wrong source pair, wrong metadata, wrong provenance, stale source revision.
3. **Transformation failure** — unit conversion, normalization, sign, indexing, canonical pair orientation.
4. **Resolution / precedence failure** — aliasing selects the wrong pair, fallback shadows explicit data, charge state disappears.
5. **Interpolation / boundary failure** — exact grid is correct but off-grid interpolation or range clipping differs.
6. **Implementation failure** — framework/QPX result disagrees with an independently computed reference.
7. **Physics-model failure** — the implementation is internally correct but the chosen approximation fails independent experimental or analytic evidence.

A batch should include cheap discriminators for the high-probability or high-cost failure classes above before runtime begins.

## 3. Evidence contract for every test

Each test should declare:

```text
Test ID
Hypothesis tested
Input/reference revision
Independent control changed
Measured quantities
Expected numeric or structural signature
PASS rule
FAIL classification
Immediate fail-branch test(s)
```

This prevents a process return code from being confused with physics evidence and prevents post-hoc acceptance rules.

## 4. Layered validation order

When a workflow contains external data or derived coefficients, validate one transformation layer at a time.

Recommended order:

```text
source data
  -> raw extraction parity
  -> metadata / provenance parity
  -> canonical key / alias resolution
  -> unit conversion
  -> interpolation / clipping
  -> derived coefficient
  -> production-path parity
  -> physics integration
```

Do not jump from source data directly to a coupled physics run when intermediate transformations can be checked independently.

## 5. Mandatory construction preflight

Every MOOSE/QPX batch containing executable inputs should perform construction validation before a full solve.

```text
P0 checker self-test / negative controls
P1 static input checks
P2 qpx-opt --check-input
P3 full runtime only after P0-P2 pass
```

Static checks should include, when relevant:

- duplicate blocks;
- reserved parsed-functor symbols;
- missing files;
- functor dependency graph;
- generated dot-functor naming;
- alias target validity;
- expected outputs/postprocessors.

A construction failure must be classified as harness/configuration evidence, not physics evidence.

### Functor example

If `ADGenericFunctorMaterial` provides property `w_O_state` with `define_dot_functors = true`, the generated derivative functor is:

```text
dw_O_state_dt
```

A consumer requesting `dO_state_dt` is a naming/dependency defect and should be caught in P1/P2 before the full solve.

## 6. Validate the checker

A validator/checker must prove that it can detect the defect class it claims to cover.

Use mutation/negative-control tests, for example:

```text
valid configuration              -> PASS
missing provider                 -> FAIL
wrong generated-dot name         -> FAIL
duplicate block                  -> FAIL
reserved parser symbol           -> FAIL
```

A checker that has not demonstrated defect-detection capability is itself an unvalidated component.

## 7. Branch-aware packaging

If the next discriminator after a plausible failure is cheap and safe, include it in the same batch.

Example:

```text
primary full case
├─ PASS -> acceptance
└─ FAIL
   ├─ static/construction evidence -> HARNESS/CONSTRUCTION
   ├─ smaller dt passes -> DT_SENSITIVE
   └─ subsystem-only discriminator
      ├─ passes -> coupling failure
      └─ fails -> base subsystem failure
```

Do not execute fail-branch physics cases after a construction preflight failure unless they provide independent construction information.

## 8. Failure-class output

A generic `FAIL` is insufficient. The batch should emit a class such as:

```text
HARNESS_OR_SCHEMA_FAIL
MISSING_FUNCTOR_FAIL
SOURCE_VALUE_FAIL
SOURCE_METADATA_FAIL
UNIT_TRANSFORM_FAIL
RESOLVER_FAIL
INTERPOLATION_OR_RANGE_POLICY_FAIL
PRODUCTION_PATH_PARITY_FAIL
PHYSICS_MODEL_FAIL
```

The output should also preserve the numeric/structural evidence needed to decide the next action without another exploratory round.

## 9. Role integration

The Manager should route source/model uncertainty to the Researcher and test sufficiency/closure questions to the Validator. See `docs/guides/manager_role_routing.md`.

The Researcher establishes external/source truth. The Validator checks coverage, false-PASS risk, and acceptance sufficiency. Predictive batch construction then turns those decisions into executable discriminators.

## 10. Measurement

Use the Work Closure Validator metrics to determine whether predictive batching improves the workflow:

- WCC / T-WCC should decrease within comparable complexity;
- EVR should decrease by packaging preflight and likely fail branches together;
- DBR should remain <= 2 for normal bounded incidents where possible;
- RWR should approach 0 as construction preflight improves;
- FBR should increase without weakening technical acceptance.

Do not reduce interaction counts by removing independent evidence or weakening canonical gates.
