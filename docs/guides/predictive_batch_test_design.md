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
  -> execution
  -> result signature
  -> immediate hypothesis decision
```

The optimization objective is not to maximize test count. It is to maximize information obtained per external execution round while keeping every test causally interpretable.

## 2. Predictive pre-mortem before execution

Before packaging a batch, list plausible ways each primary test can fail. At minimum separate:

1. **Harness / construction failure** — malformed input, duplicate block, missing output, parser collision, wrong executable path.
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
  -> QPX/MOOSE implementation parity
  -> coupled physics integration
```

A downstream failure must not be interpreted as physics evidence until its prerequisite layers have passed.

## 5. Branch-aware batching rule

If the likely next diagnostic is cheap, deterministic, and independent of the failed solver state, include it in the same bundle.

Example:

```text
T1 source parity
  FAIL -> T1F1 raw-token diff
          T1F2 pair-orientation check
          T1F3 unit sentinel check

T2 resolver
  FAIL -> T2F1 identity-map static check
          T2F2 precedence trace
          T2F3 commutativity / charge-preservation check
```

Do not include expensive interaction tests before primitive hypotheses are tested. Primitive failure causes should be isolated first.

## 6. Harness protection

Every external-runtime bundle should, where practical, contain static preflight checks for failure modes that do not require the solver:

- duplicate object/block names;
- invalid or reserved parser symbols;
- missing referenced files;
- missing expected output columns;
- duplicate or unknown species identifiers;
- unresolved aliases;
- inconsistent pair keys;
- impossible charge-state collapse;
- stale previous outputs.

Harness failures are recorded as rework/incident evidence, not as physics FAIL.

## 7. Data-validation specialization

For transport, thermodynamic, chemistry, or other imported databases, separate **raw-source parity** from **derived-value parity**.

### Raw-source parity

Validate exactly what the upstream source declares:

- pair/species identity;
- temperature grid;
- tabulated values;
- units;
- metadata such as `multpi`;
- reference/provenance;
- explicit-vs-default status.

### Derived-value parity

Then validate QPX-side representation independently:

- SI conversion;
- interpolation;
- clipping/extrapolation policy;
- alias/pair resolution;
- derived binary coefficient;
- mixture coefficient.

A raw-value mismatch and a unit-conversion mismatch must produce different result signatures.

## 8. Resolver invariants

For pair databases with aliases/fallbacks, require the resolver itself to have canonical regressions.

Typical invariants:

```text
resolve(a,b) == resolve(b,a)
resolve(identity(a), identity(b)) is deterministic
explicit pair > fallback
charged identity is never silently collapsed to neutral
excited-state collapse affects only the declared excitation dimension
all physical pairs resolve to either explicit data or an explicitly named fallback
```

The selected data source should be observable in diagnostics: for example `EXPLICIT`, `LANGEVIN_FALLBACK`, or `DEBYE_HUCKEL_DEFAULT`.

## 9. Predictive Batch A template for imported transport data

Use this template before coupled MOOSE/QPX runtime tests.

### A0 — schema/static preflight

Predicted failures:
- duplicate species/aliases;
- unknown target identities;
- charged species mapped to neutral identities;
- malformed pair keys.

Tests:
- unique identifier check;
- alias target existence;
- charge-preservation invariant;
- canonical pair-key normalization.

### A1 — source inventory and provenance parity

Primary test:
- compare every required explicit source pair with the upstream source.

Predicted fail branches:
- **A1F1 orientation:** `(a,b)` vs `(b,a)` canonicalization error;
- **A1F2 metadata:** temperature grid, units, `multpi`, reference mismatch;
- **A1F3 completeness:** expected explicit pair accidentally classified as missing/fallback.

### A2 — raw-to-runtime unit parity

Primary test:
- compare known grid-point sentinels before and after conversion.

Predicted fail branches:
- missing `pi` factor;
- Å²-to-m² conversion error;
- conversion applied twice;
- raw table already converted but treated as source units.

Keep a raw-source value and its expected runtime-SI value in the same result signature.

### A3 — resolver exhaustive test

Primary test:
- enumerate every unordered physical-species pair.

Predicted fail branches:
- **A3F1 identity map:** wrong physical-to-transport alias;
- **A3F2 precedence:** generic fallback shadows explicit pair;
- **A3F3 symmetry:** `resolve(a,b) != resolve(b,a)`;
- **A3F4 charge preservation:** charged identity disappears;
- **A3F5 excitation collapse:** excited neutral does not collapse only to its declared parent.

### A4 — interpolation and range-policy parity

Primary tests:
- exact grid points;
- one or more off-grid points;
- lower/upper range boundary behavior.

Predicted fail branches:
- wrong interpolation method;
- pair-specific temperature grid mixed with another pair;
- clipping/extrapolation mismatch;
- non-monotonic data incorrectly forced to be monotonic.

Do not impose monotonicity unless the underlying physics/source requires it. Compare against the declared upstream behavior.

### A5 — explicit-vs-default provenance trace

Primary test:
- required explicit pairs must report `EXPLICIT`;
- genuinely missing pairs must report the declared fallback class.

Predicted fail branches:
- fallback used despite available explicit data;
- fallback class selected from neutral identity after charge loss;
- unresolved pair silently replaced by a generic neutral pair.

## 10. Batch decision rule

A batch result should distinguish at least these states:

```text
BATCH_PASS
HARNESS_FAIL
SOURCE_PARITY_FAIL
METADATA_FAIL
UNIT_TRANSFORM_FAIL
RESOLVER_FAIL
INTERPOLATION_FAIL
PRECEDENCE_FAIL
```

Do not collapse these into one generic FAIL.

If all primitive tests pass, proceed to derived-coefficient and coupled-runtime validation. If one primitive class fails, restrict the next action to that class.

## 11. Measurement and workflow improvement

Continue the issue-local Work Closure Validator metrics. Predictive batching is successful when, for comparable complexity:

- WCC and T-WCC trend downward;
- DBR stays small because likely branches are predeclared;
- RWR decreases because static/harness checks catch construction defects before user runtime;
- FBR remains `yes` and increasingly represents real branch coverage rather than only a written fallback note;
- EVR is reserved for actual external runtime/evidence rounds, not source-research-only work.

Do not reduce validation quality merely to reduce WCC.

## 12. Promotion rule

When a predictive branch catches a real defect:

1. preserve incident-specific history in the issue/incident log;
2. decide whether the failure mode is reusable;
3. if reusable, promote the discriminator or static check into the default batch template;
4. update this guide when the new test replaces a recurrent user-runtime round trip.

The guide should therefore evolve from observed failure patterns rather than remain a fixed checklist.
