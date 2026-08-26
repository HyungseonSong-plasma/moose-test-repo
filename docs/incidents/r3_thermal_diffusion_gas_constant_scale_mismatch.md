# R3 thermal-diffusion D_T gas-constant scale mismatch

**Status:** OPEN  
**Issue:** #13 `oxygen-heavy-transport-db`  
**Class:** implementation/host-constant consistency  

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

The six cases were `attr_base`, `attr_ne_low`, `attr_ne_high`, `attr_te_low`, `attr_te_high`, and `rep_base`.

## H1 -> T1: Debye-Huckel/state implementation error

**H1:** The runtime Debye-Huckel `Te/ne` dependence or attractive/repulsive branch is wrong.

**T1 evidence:**
- `kT` follows the independent reference closely;
- `ne` sensitivity passes (`183.326269%` output change);
- `Te` sensitivity passes (`39.087466%`);
- attractive/repulsive discriminator passes (`99.994829%`);
- the `D_T` discrepancy is nearly identical in relative magnitude for all six states and both Coulomb branches.

**Decision:** H1 REJECTED.

A state/branch defect would not naturally produce one invariant multiplicative scale in only the final mass-flux coefficient while preserving `kT` and all state sensitivities.

## H2 -> T2: host gas-constant scale mismatch

**H2:** The final density conversion uses a host `R` value inconsistent with the `k_B` and `N_A` constants already used in the same transport calculation.

The original code used:

```cpp
const ADReal rho = p * mean_molar_mass / (QPX_CONSTANTS::R * T);
```

while particle masses and number-density terms already use `QPX_CONSTANTS::N_A` and `QPX_CONSTANTS::k_boltz`.

From the runtime `D_T`/reference ratio,

```text
R_eff = R_reference * D_T_reference / D_T_QPX
```

collapses across all six test cases to approximately `8.31456 J/(mol K)`. Re-evaluating the reference outputs with this single scale reproduces the observed runtime values, e.g.

```text
attr_base: 2.355045666e-15 -> 2.355018083e-15
attr_ne_low: 1.080825243e-15 -> 1.080812584e-15
attr_ne_high: -2.066335981e-15 -> -2.066311780e-15
attr_te_low: 2.960054397e-15 -> 2.960019729e-15
attr_te_high: 1.803044149e-15 -> 1.803023032e-15
rep_base: 4.554535482e-11 -> 4.554482138e-11
```

These values match the user-local runtime signature to the printed precision.

**Decision:** H2 SUPPORTED.

## Fix candidate

Keep this material internally consistent with its own microscopic constants:

```cpp
const Real R_transport = QPX_CONSTANTS::k_boltz * QPX_CONSTANTS::N_A;
const ADReal rho = p * mean_molar_mass / (R_transport * T);
```

Do not change the global QPX constant definition in this incident; that would have a broader scope and requires separate impact analysis.

## Regression requirement

Rebuild `qpx-opt` with the patched material and rerun the same R3 dynamic batch. Required closure signature:

```text
R3E_SOURCE_CONTRACT: PASS
R3F_NEUTRAL_BACKWARD_COMPAT: PASS
R3F_CHARGED_DYNAMIC_CONSTRUCTION: PASS
R3G_CONDITIONAL_REQUIRED_INPUTS: PASS
R3H: PASS
R3I: PASS
R3_DYNAMIC_IMPLEMENTATION_PASS
```

The incident remains OPEN until the user-local rebuilt QPX run confirms the fix.
