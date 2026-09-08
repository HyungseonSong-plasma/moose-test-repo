# Incident: validator representation-equivalence false fail

**Incident ID:** `INC-VALIDATOR-EQUIV-001`  
**Date:** 2026-08-29  
**Status:** CLOSED — root cause isolated and self-test repaired  
**Associated work:** Issue #43 `QVT multiphysics space-time scale and coupling architecture audit`  
**Failure class:** `VALIDATOR_SELFTEST_FAIL`; no QPX physics execution involved

## Symptom

The CORE-16-aware fast-plasma self-test reported:

```text
EXECUTION_CONTRACT_SELFTEST: PASS
ISSUE43_FAST_V3_SELFTEST: FAIL (wrong dtmin: expected 1e-14, got 1.0000000000000002e-14)
ISSUE43_FAST_V4_SELFTEST: FAIL (v3 self-test failed)
```

The generated fixed-step contract used:

```text
dt = 1e-13
dtmin = 0.1 * dt
```

and the serialized/reparsed value was `1.0000000000000002e-14`, which is numerically equivalent to the intended `1e-14` at floating-point representation precision.

## Root cause

The validator self-test required exact Python floating-point equality:

```python
float(actual) == expected
```

That comparison was stronger than the representation contract. Decimal text generation, binary floating-point arithmetic, formatting, and reparsing are not guaranteed to reproduce the same binary value as an independently written decimal literal even when both represent the same intended numerical control.

Therefore the self-test rejected a semantics-preserving representation difference.

This is not a numerical-contract violation. In particular, it is categorically different from a material change such as:

```text
requested dt = 1e-13
effective dtmin = 1e-12
```

which must remain a hard P1 contract failure.

## Fix

The self-test now uses a representation-level comparison:

```python
math.isclose(actual, expected, rel_tol=1e-15, abs_tol=0.0)
```

The tolerance is intentionally limited to floating-point representation noise. Existing negative controls still require a true `dt < dtmin` contradiction to fail.

## Relation to prior incidents

This exact symptom is new, but the failure pattern already existed in several forms:

- `step2_eos_validation_aggregation_error.md`: midpoint of extrema was treated as equivalent to a spatial average;
- `r3_source_contract_classifier_false_ambiguous.md`: one exact C++ token sequence was treated as equivalent to semantic source capability;
- `r3_thermal_diffusion_gas_constant_scale_mismatch.md` and `r4_a6_production_oracle_constant_convention_mismatch.md`: different source/host numerical conventions were treated as interchangeable;
- `step3_initial_csv_zero_row_acceptance_error.md`: an initialization observation was treated as equivalent to a completed physical timestep;
- VAL-16 already prevented exact continuous/discrete equality assumptions in temporal identities.

The recurring abstraction is:

```text
validator comparison semantics
must not be stronger than the equivalence guaranteed by the representation,
and must not be weaker than the equivalence required by the scientific claim.
```

## Reusable prevention rule

Before a validator compares two values, artifacts, states, or source representations, classify the required equivalence. Typical classes include:

```text
syntax / byte exact
identifier / enum exact
discrete mathematical exact
representation-equivalent numeric
numerical tolerance
convergence / refinement equivalence
physical-model tolerance
```

Use exact equality only when the producing representation and the claim both require exact identity. Otherwise use the narrowest justified equivalence relation and mutation-test that a materially different value still fails.

## Closure evidence

The immediate self-test repair replaced exact float comparison with `math.isclose(..., rel_tol=1e-15, abs_tol=0.0)` while preserving the existing `dtmin=1e-12` negative-control rejection.

No plasma physics, timestep selection, solver control, MOOSE model, or QPX implementation was changed to resolve this incident.
