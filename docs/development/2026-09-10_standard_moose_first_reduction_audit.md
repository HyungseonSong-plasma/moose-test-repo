# Standard MOOSE First reduction audit — 2026-09-10

## Decision

Adopt **Standard MOOSE First** for `physics_app`.

A custom C++ `MooseObject` is justified only when the required scientific/numerical contract cannot be expressed with pinned standard MOOSE objects without weakening semantics, AD coupling, validation, bounds policy, conservation, or ownership.

Pinned framework baseline:

```text
MOOSE = 9f388366ccf38b9c34542ec5561198249fde0ac9
```

This is a reduction/refactor policy. It must not change accepted physics semantics.

## First reduction — E8 reaction-energy projection

Pinned MOOSE `FVCoupledForce` accepts a `MooseFunctorName v`, evaluates it as `ADReal`, and contributes

```text
residual = -coef * v
```

Therefore

```text
S_hat = -Delta_epsilon_eV * N_A * R_k / (n_ref * epsilon_ref_eV)
residual = -S_hat
```

is represented directly as

```text
type = FVCoupledForce
v = R_k
coef = -Delta_epsilon_eV * N_A / (n_ref * epsilon_ref_eV)
```

with no custom reaction-energy kernel and no duplicate kinetic-rate evaluation.

### A/B acceptance

Accepted custom oracle repository:

```text
b882211eb24a94bb645d0c13ecd96badc2c35095
```

Standard-MOOSE A/B repository:

```text
cdc8a9d5b3898a10706a6bfb1f4d3518dd1170a9
workflow run = 34505556177 / SUCCESS
artifact = standard-moose-energy-projection-ab-evidence
artifact id = 10163796796
artifact digest = sha256:0c80a4712c02dfbbd5c5f359bd1008ab75d1a998d502e7bca6e86c26f9634246
```

The A/B discriminator instantiated no `PhysicsFVElectronReactionEnergySource` and returned **exact zero delta** for every compared EI10 and EI16 final-state quantity.

```text
EI10 n_epsilon_hat = 0.99198106194124
EI10 mean_en       = 5.6867893526543 eV
EI10 R_O2s         = 0.0078133117564827 mol/(m^3 s)

EI16 n_e_hat       = 1.1016960590289
EI16 n_epsilon_hat = 0.78606212855788
EI16 mean_en       = 4.0903346174113 eV
EI16 R_ion_O2      = 0.016887027897333 mol/(m^3 s)
```

All recorded `delta_from_accepted_oracle` entries are `0.0`.

Frozen coefficients:

```text
EI10 coef = -10263174.32182753
EI16 coef = -126687699.40761518
```

### Nonnegative-progress guard

`FVCoupledForce` itself is an algebraic projector and does not own a `R_k >= 0` error check.

The reduction is accepted only on the existing **shared canonical path**, where the upstream reaction-rate/source owners already constrain the controlled reaction progress. Independent energy-only use of these E8 configurations is forbidden. This avoids turning the standard source kernel into an alternate kinetics path.

## Reduction classification

| Custom surface | Disposition | Reason |
|---|---|---|
| `PhysicsFVElectronReactionEnergySource` | **RETIRE** | Exact-zero A/B against accepted EI10/EI16 oracles; `FVCoupledForce` is sufficient. |
| `PhysicsFVElectronReactionSource` | **NEXT reduction candidate** | Pure normalization/source projection; test direct standard functor source A/B. |
| `PhysicsFVSpeciesReactionSource` | **NEXT reduction candidate** | Pure volumetric source projection; test mass-fraction equation A/B. |
| `PhysicsO2IonizationSourceMaterial` | **NEXT reduction candidate** | Algebraic stoichiometric projection from one canonical progress. |
| `PhysicsO2sExcitationSourceMaterial` | **NEXT reduction candidate** | Algebraic stoichiometric projection from one canonical progress. |
| `PhysicsElectronImpactO2sExcitationMaterial` | **NEXT reduction candidate** | Frozen constant-rate algebra; likely expressible with `ADParsedFunctorMaterial`. |
| `PhysicsElectronMeanEnergyMaterial` | **AUDIT** | Algebra is parsable, but positivity/error semantics must be reproduced before removal. |
| `PhysicsElectronImpactIonizationMaterial` | **KEEP for now** | Owns strict tabulated interpolation and explicit fail-on-out-of-range behavior. |
| transport lookup / cross-section table owners | **KEEP for now** | Strict data/provenance/bounds behavior must be preserved. |
| drift/diffusion/conservative heavy transport/wall/SEE | **SEPARATE audit** | Encode discretization or boundary semantics; require dedicated equivalence tests. |

## Follow-up order

1. Retire custom E8 energy projector after canonical post-removal regression. **CURRENT**
2. Electron and heavy source projectors -> standard functor source kernels.
3. R3 constant-rate and stoichiometric source materials -> parsed/standard composition.
4. Mean-energy bridge only after equivalent positivity/error handling is frozen.
5. Strict tabulated kinetics only if standard MOOSE can reproduce exact fail-on-bounds and AD behavior.
6. Transport/discretization/boundary custom objects in separate bounded audits.

No object is removed merely to reduce C++ line count. Scientific and numerical contract equivalence is the gate.
