# R4/R5 A6 production-oracle constant convention mismatch

**Status:** CLOSED  
**Issue:** #13 `oxygen-heavy-transport-db`  
**Class:** validation-reference / production-parity constant convention

## Symptom

The first user-local R4/R5 canonical run passed P0, A0-A5, A7, and every A6 construction/runtime call, but A6 numeric parity failed with a transport-class-dependent error vector from about `1.45e-6` to `3.97e-5`.

## H1 -> T1: production QPX implementation defect

A0-A5 passed, all 49 ordered resolver queries had the intended provenance, A7 detected all injected defects, every A6 runtime call returned zero, and the previously accepted R3 dynamic implementation already matched an independent runtime oracle below `5e-8`.

**Decision:** H1 REJECTED.

## H2 -> T2: output formatting / CSV precision

The later v2 attempt to force top-level `Outputs/precision` and `Outputs/scientific_notation` was itself invalid for the user's MOOSE build and became a separate harness/construction incident. It was not the cause of the original v1 parity vector.

**Decision:** H2 REJECTED as the v1 physics-parity mechanism.

## H3 -> T3: historical source constants leaked into the production-parity oracle

The v1 A6 independent oracle reused historical numerical constants from pinned Mutation++ source code in the QPX production-parity calculation. The accepted QPX/R3 implementation uses the QPX production numerical convention. Reintroducing the historical constants into the corrected oracle reproduced the actual v1 failure vector within about `2.5e-8`.

**Decision:** H3 SUPPORTED.

## Corrective action

- Keep A1/A2 pinned to Mutation++ source data/provenance.
- Keep A6 algorithmically independent, but use the numerical constants of the accepted QPX production convention for production parity.
- Keep the strict `2e-7` parity gate.
- Mutation-test the historical-constant substitution before runtime.
- Respect the production constructor semantics: if the active species set contains any charged species, its charged self-pair may require `electron_temperature` and `electron_number_density` even when the selected cross-pair is ion-neutral.
- Do not use unsupported top-level output-format parameters merely to increase precision.

## Closure evidence

The corrected v3 user-local run produced:

```text
R4_R5_ORACLE_CONSTANT_SELFTEST: PASS
R4_R5_HARNESS_SELFTEST: PASS
A0_SCHEMA_STATIC: PASS
A1_SOURCE_PROVENANCE: PASS
A2_RAW_TO_SI: PASS
A3_EXHAUSTIVE_RESOLVER: PASS
A4_INTERPOLATION_RANGE: PASS
A5_PROVENANCE_PRECEDENCE: PASS
A7_VALIDATOR_MUTATION_SELFTEST: PASS
A6_QPX_PRODUCTION_PATH: PASS
BATCH_A_PASS
R4_R5_PASS
```

All seven A6 runtime cases had maximum relative error `2.526e-08`, comfortably below `2e-7`. Dimensionless `kT` parity was approximately `1e-14` or better.

## Reusable lesson

Source-data provenance and production-parity validation answer different questions. An independent production oracle should not silently inherit historical upstream numerical constants when the production implementation intentionally uses a different host convention. Preserve algorithmic independence while matching the production numerical contract, and use mutation tests to prove the distinction is observable.
