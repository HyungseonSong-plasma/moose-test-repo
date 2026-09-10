# Standard MOOSE First reduction audit — 2026-09-10

## Decision

Adopt **Standard MOOSE First** for `physics_app`.

A custom C++ `MooseObject` is justified only when the required scientific/numerical contract cannot be expressed with pinned standard MOOSE objects without weakening semantics, AD coupling, validation, bounds policy, conservation, or ownership.

The pinned framework baseline for this audit is:

```text
MOOSE = 9f388366ccf38b9c34542ec5561198249fde0ac9
```

This is a reduction/refactor policy only. It must not change accepted physics semantics.

## Exact standard capability used first

Pinned MOOSE `FVCoupledForce` accepts a `MooseFunctorName v`, evaluates it as `ADReal`, and contributes

```text
residual = -coef * v
```

Therefore the accepted E8 reaction-energy mapping

```text
S_hat = -Delta_epsilon_eV * N_A * R_k / (n_ref * epsilon_ref_eV)
residual = -S_hat
```

can be represented directly as

```text
type = FVCoupledForce
v = R_k
coef = -Delta_epsilon_eV * N_A / (n_ref * epsilon_ref_eV)
```

without a custom energy-source kernel and without recomputing kinetics.

## Reduction classification

| Current custom surface | Disposition | Reason |
|---|---|---|
| `PhysicsFVElectronReactionEnergySource` | **REMOVE after A/B PASS** | Pure constant scaling/sign projection of an existing AD functor; `FVCoupledForce` is exactly sufficient. |
| `PhysicsFVElectronReactionSource` | **NEXT reduction candidate** | Pure normalized source projection; likely direct `FVCoupledForce` with `v=canonical source/progress`. Requires A/B before removal. |
| `PhysicsFVSpeciesReactionSource` | **NEXT reduction candidate** | Pure volumetric source projection; likely direct `FVCoupledForce`. Requires mass-fraction equation A/B. |
| `PhysicsO2IonizationSourceMaterial` | **NEXT reduction candidate** | Algebraic stoichiometric projection from one canonical progress. Can likely move coefficients directly to standard source kernels. |
| `PhysicsO2sExcitationSourceMaterial` | **NEXT reduction candidate** | Same algebraic projector pattern. |
| `PhysicsElectronImpactO2sExcitationMaterial` | **NEXT reduction candidate** | Frozen constant-rate algebra; `ADParsedFunctorMaterial` can express it. Preserve exact `R_O2s` ownership and coefficient identity. |
| `PhysicsElectronMeanEnergyMaterial` | **AUDIT** | Algebra is standard-parsable, but current positivity/error semantics must be reproduced before removal. |
| `PhysicsElectronImpactIonizationMaterial` | **KEEP for now** | Owns strict tabulated interpolation with explicit out-of-range error. No standard replacement accepted until identical bounds and AD semantics are demonstrated. |
| transport lookup / cross-section table owners | **KEEP for now** | Same strict data/provenance/bounds concern. |
| drift, diffusion, conservative heavy transport, wall/SEE objects | **SEPARATE audit** | These encode discretization/boundary semantics; not safe to classify as algebraic wrappers without dedicated equivalence tests. |

## First A/B gate

Compare the already accepted custom E8 vectors at repository
`b882211eb24a94bb645d0c13ecd96badc2c35095`
against a standard-MOOSE implementation that instantiates no
`PhysicsFVElectronReactionEnergySource`.

Frozen accepted oracle:

```text
EI10 n_epsilon_hat = 0.99198106194124
EI10 mean_en       = 5.6867893526543 eV
EI10 R_O2s         = 0.0078133117564827 mol/(m^3 s)

EI16 n_e_hat       = 1.1016960590289
EI16 n_epsilon_hat = 0.78606212855788
EI16 mean_en       = 4.0903346174113 eV
EI16 R_ion_O2      = 0.016887027897333 mol/(m^3 s)
```

Standard coefficients:

```text
EI10 coef = -0.977 * N_A / (1e16 * 5.73276)
           = -10263174.32182753

EI16 coef = -12.06 * N_A / (1e16 * 5.73276)
           = -126687699.40761518
```

A/B PASS requires the same final nonlinear vectors within the existing controlled-discriminator tolerance, while preserving the same upstream canonical reaction-progress owners.

## Follow-up order

1. E8 custom energy projector -> `FVCoupledForce`.
2. Electron and heavy source projectors -> standard functor source kernels.
3. R3 constant-rate and stoichiometric source materials -> parsed/standard composition.
4. Mean-energy bridge only after equivalent positivity/error handling is frozen.
5. Strict tabulated kinetics only if standard MOOSE can reproduce exact fail-on-bounds and AD behavior.
6. Transport/discretization/boundary custom objects in separate bounded audits.

No source is removed merely to reduce C++ line count. Scientific contract equivalence is the gate.
