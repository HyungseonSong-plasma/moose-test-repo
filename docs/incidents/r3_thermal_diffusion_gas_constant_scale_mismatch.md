# R3 thermal-diffusion D_T gas-constant scale mismatch

**Status:** CLOSED  
**Issue:** #13 `oxygen-heavy-transport-db`  
**Class:** validation-reference / host-constant convention  

## Symptom

User-local R3 dynamic Debye-Huckel validation passed construction, conditional `Te/ne` requirements, source contract, and dynamic state sensitivity, but failed strict end-to-end `D_T` parity:

```text
R3E_SOURCE_CONTRACT: PASS
R3F_NEUTRAL_BACKWARD_COMPAT: PASS
R3F_CHARGED_DYNAMIC_CONSTRUCTION: PASS
R3G_CONDITIONAL_REQUIRED_INPUTS: PASS
R3I: PASS
R3H: FAIL
max_rel_error ~= 1.169e-05 for every state/branch case
```

## H1 -> T1: Debye-Huckel/state implementation error

**H1:** Runtime Debye-Huckel `Te/ne` dependence or attractive/repulsive branch is wrong.

**T1 evidence:**
- `kT` remained tightly aligned with the independent reference;
- `ne` sensitivity passed (`183.326269%`);
- `Te` sensitivity passed (`39.087466%`);
- attractive/repulsive discriminator passed (`99.994829%`);
- `D_T` showed one nearly invariant multiplicative offset across all six cases.

**Decision:** H1 REJECTED.

## H2 -> T2: source defect in the QPX EOS gas constant

The first diagnosis treated the invariant `D_T` scale as a production-source defect and replaced

```cpp
QPX_CONSTANTS::R
```

with

```cpp
QPX_CONSTANTS::k_boltz * QPX_CONSTANTS::N_A
```

in the final density conversion.

The user rebuilt and reran the full R3 batch. Construction and all dynamic-state gates still passed, but `R3H` again failed by the same ~`1.169e-05` magnitude, now on the opposite side of the reference. Comparing the pre-patch and post-patch runtime outputs showed the only moved quantity was the expected final `D_T` scale.

**Decision:** H2 REJECTED.

## H3 -> T3: oracle gas-constant convention mismatch

The existing QPX production path uses

```cpp
const ADReal rho = p * mean_molar_mass / (QPX_CONSTANTS::R * T);
```

and the project host EOS convention is `R = 8.31456 J/(mol K)`. The original Python R3 oracle instead used modern exact

```text
R = k_B * N_A = 8.314462618... J/(mol K)
```

for the final EOS density.

From the original user-local R3 runtime, the effective host constant inferred from every `D_T` case was approximately

```text
8.31456 J/(mol K)
```

and substituting that value only in the oracle's final EOS density reproduced the original QPX outputs to the printed precision. The wrong-oracle mutation predicts a relative `D_T` mismatch of `1.1712344e-05`, matching the observed false-fail scale.

**Decision:** H3 SUPPORTED.

## Corrective action

1. Retain the established QPX host EOS expression:

```cpp
const ADReal rho = p * mean_molar_mass / (QPX_CONSTANTS::R * T);
```

2. Use the QPX host EOS convention (`8.31456 J/(mol K)`) only in the final QPX-side `D_T` oracle conversion while keeping the microscopic collision/state model independent.
3. Keep the strict `2e-7` numeric gate; do not loosen tolerance.
4. Keep a mutation self-test that substitutes the modern-exact gas constant and requires the resulting ~`1e-5` error to be detected.

## Closure evidence

User-local rebuilt `qpx-opt` v3 regression produced:

```text
R3_ORACLE_CONSTANT_SELFTEST: PASS
R3E_SOURCE_CONTRACT: PASS
R3F_NEUTRAL_BACKWARD_COMPAT: PASS
R3F_CHARGED_DYNAMIC_CONSTRUCTION: PASS
R3G_CONDITIONAL_REQUIRED_INPUTS: PASS
R3H: PASS
R3I: PASS
R3_DYNAMIC_IMPLEMENTATION_PASS
```

Strict end-to-end maximum relative errors were `2.42e-08` to `4.54e-08`, well below the `2e-7` acceptance limit. Dynamic-state discrimination remained strong:

```text
ne state output change:                  183.326269%
Te state output change:                   39.087466%
attractive vs repulsive output change:    99.994829%
```

The production-source gas-constant change was reverted; the defect was in the validation reference convention, not the Debye-Huckel implementation.

## Reusable lesson

When validating a subsystem against an independent oracle, separate **source-model constants** from **host-framework conventions**. A uniform multiplicative discrepancy across unrelated physics states is a strong discriminator for a downstream unit/constant/convention mismatch. Before modifying production physics, infer the effective scale from runtime evidence and mutation-test the oracle convention.
