# Issue #309 — grounded electron sheath owner migration

**Status:** validation pending  
**Scientific semantics:** preserved from accepted Issue #215/#217 evidence  
**Migration class:** representation mismatch -> generic thin adapter

## Source owners retired

The following sheath-specific C++ ownership is retired by #309:

- `PhysicsFVElectronGroundedSheathCollectionBC`
- `PhysicsFVElectronGroundedSheathEnergyBC`
- `PhysicsGroundedElectronSheathFlux.h`

References to those paths in older provenance documents identify historical accepted revisions only. They are not canonical current callers or owners.

## Capability census

The accepted Issue #215/#217 sheath closure requires the **adjacent plasma-cell state** at a grounded FV Dirichlet wall.

Standard `FVFunctorNeumannBC` evaluates its flux functor on the boundary face. For an FV variable with a Dirichlet boundary condition this can resolve the boundary value rather than the required adjacent-cell value. Therefore direct replacement by:

```text
ADParsedFunctorMaterial + FVFunctorNeumannBC
```

is classified:

```text
REPRESENTATION_MISMATCH
```

rather than a physics capability gap.

## Current realization

Sheath physics is declarative:

```text
ADParsedFunctorMaterial
  particle:
    Gamma_p = 0.25 n_e vbar exp(-DeltaPhi/Te)
    Te = (2/3) mean_energy

  energy:
    Gamma_energy = Gamma_p (2 Te + DeltaPhi) / epsilon_ref
```

Issue #217's energy material consumes the same parsed particle-flux functor directly, preserving the same-collected-population dependency.

Boundary application uses one generic adapter:

```text
PhysicsFVCellFunctorNeumannBC
```

The adapter owns only:

```text
arbitrary flux functor
+ arbitrary factor
+ adjacent FV cell evaluation
```

It contains no electron, sheath, Boltzmann, energy, species, or SEE semantics.

## Branch-validity preservation

The historical electron-repelling branch remains a runtime acceptance gate:

```text
phi_plasma >= -1e-10 V
```

The parsed closure uses `max(phi,0)` only to keep the algebra defined during nonlinear evaluation; accepted Issue #215/#217 evidence still fails closed if the converged trajectory leaves the historical branch.

## Validation ladder

```text
zero live callers to retired owners
-> Python/static contract
-> Physics Unity build
-> Issue215/217 self-tests
-> sheath smoke --check-input
-> Issue215 runtime acceptance
-> Issue217 runtime acceptance
-> exact-head repository CI
```

Successful migration establishes implementation parity only. It introduces no new plasma-physics acceptance claim.
