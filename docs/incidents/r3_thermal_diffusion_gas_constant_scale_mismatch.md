# R3 thermal-diffusion D_T gas-constant scale mismatch

**Status:** OPEN  
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
- `kT` remains tightly aligned with the independent reference;
- `ne` sensitivity passes (`183.326269%`);
- `Te` sensitivity passes (`39.087466%`);
- attractive/repulsive discriminator passes (`99.994829%`);
- `D_T` shows one nearly invariant multiplicative offset across all six cases.

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

The user rebuilt and reran the full R3 batch. Construction and all dynamic-state gates still passed, but `R3H` again failed by the same ~`1.169e-05` magnitude, now on the opposite side of the reference. Comparing the pre-patch and post-patch runtime outputs shows the only moved quantity is the expected final `D_T` scale.

This falsifies the source-fix hypothesis.

**Decision:** H2 REJECTED.

## H3 -> T3: oracle gas-constant convention mismatch

The existing QPX production path uses

```cpp
const ADReal rho = p * mean_molar_mass / (QPX_CONSTANTS::R * T);
```

and other QPX heavy-species code uses the same host molar-gas-constant convention. The Python R3 oracle instead used modern exact

```text
R = k_B * N_A = 8.314462618... J/(mol K)
```

for the final EOS density.

From the original user-local R3 runtime, the effective host constant inferred from every `D_T` case is approximately

```text
8.31456 J/(mol K)
```

and substituting that value only in the oracle's final EOS density reproduces the original QPX outputs to the printed precision. Example:

```text
attr_base reference with modern R:  2.355045666e-15
attr_base reference with QPX R:     2.355018083e-15
user-local original QPX:            2.355018e-15
```

The wrong-oracle mutation produces a predicted relative error of `1.1712344e-05`, matching the observed false-fail scale.

**Decision:** H3 SUPPORTED.

## Corrective action

1. Revert the local R3 production-source experiment and retain the established QPX host EOS expression:

```cpp
const ADReal rho = p * mean_molar_mass / (QPX_CONSTANTS::R * T);
```

2. Correct the independent R3 oracle so the final QPX-side `D_T` comparison uses the QPX host EOS convention (`8.31456 J/(mol K)`), while keeping the microscopic collision/state model independent.
3. Keep the original strict numeric gate (`2e-7`); do **not** loosen tolerance to hide the convention mismatch.
4. Add an oracle mutation self-test requiring the modern-exact-R substitution to be detected as a ~`1e-5` `D_T` error.

## Regression requirement

Rebuild `qpx-opt` with the reverted QPX EOS expression and rerun the corrected R3 v3 batch. Required closure signature:

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

The incident remains OPEN until user-local v3 evidence confirms the corrected oracle/source combination.
