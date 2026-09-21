# Issue #94 — R3 electron diffusion assembly localization

This workspace continues the Issue #93 Outcome B handoff. It localizes the
constant-state electron diffusion residual/Jacobian inconsistency without
assuming that MOOSE `FVDiffusion`, generic functor coupling, or
`QPXElectronTransportLookupMaterial` is the owner in advance.

## Frozen diagnostic state

```text
real qvt.msh
n_e = 1e16 m^-3 uniform
p = 1.33322 Pa
T_g = 600 K
mean electron energy = 5.73276 eV
D_e = 41257.29899041419 m^2/s
mu_e = 9755.114369721427 m^2/(V s)
E = 0
Poisson OFF
no wall/surface-reaction physics
```

The invariant under test is:

```text
grad(n_e) = 0
D_e = spatially constant
-> interior bulk diffusion flux = 0
```

Issue #93 established that time-only passes, time+diffusion fails with a flat
`1.197516979581` residual, excluding named plasma interfaces from
`FVDiffusion` leaves that residual unchanged, and the assembled C2 Jacobian
differs from PETSc finite differences by about 3.7%.

## L0-L3 residual localization

`localization.py` constructs all cases from the accepted Issue #93 J2
derivatives and preserves the same mesh/table/expected-observable identity.

```text
L0  exact J2 C1
    time-only control

L1  exact J2 C2 except:
    FVDiffusion coeff = 41257.29899041419
    numeric MooseFunctorName
    QPX lookup may remain for unchanged observables, but it does not own
    the diffusion residual coefficient

L2  exact J2 C2 except:
    QPXElectronTransportLookupMaterial is replaced by ADGenericFunctorMaterial
    supplying frozen electron_mobility and electron_diffusion constants

L3  exact J2 C2
    QPXElectronTransportLookupMaterial owns electron_diffusion
```

The current MOOSE `FVDiffusion` contract accepts `coeff` as a
`MooseFunctorName`, including a number, variable, functor material property,
function, or postprocessor. L1 therefore bypasses the named material/functor
coefficient path rather than approximating it with another custom object.

## Decision order

```text
L0 fails
  -> current-executable time-only control regression / HOLD

L0 passes, L1 fails
  -> framework FV diffusion / block / geometry assembly favored

L0,L1 pass, L2 fails
  -> generic functor/material coupling favored

L0,L1,L2 pass, L3 fails
  -> QPX electron transport lookup functor/material favored

L0-L3 all pass
  -> residual contract no longer reproduces
  -> Jacobian-only follow-up becomes the selected owner
```

The batch stops at the first failing residual owner. It does not run a Jacobian
sweep and does not introduce surface-reaction physics.

## EVR protection

All L0-L3 inputs are constructed and all four `--check-input` P2 calls complete
before any P3 launch. A P2 construction/framework-contract failure consumes no
Issue #94 scientific EVR.

Once L0 P3 launches, the adaptive L0->L3 batch is one governed Issue #94
scientific result return and consumes EVR1 regardless of how many predeclared
cases are needed before the first failure.

## Execution

```bash
python -m experiments.Issue94_r3_electron_diffusion_localization.localization \
  --qpx "$QPX_OPT"
```

Generated artifacts are written under `/tmp/issue94_localization_*` unless
`--work-dir` is supplied. `summary.json` records P2/P3 results, residual
trajectories, accepted checker results, the first failing case, decision,
hypothesis state, and EVR accounting.

## Surface-reaction policy

COMSOL-parity plasma-wall surface-reaction/wall-flux physics remains required
later, but it is intentionally excluded from this constant-state bulk
localization. It must not be used to mask the current residual/Jacobian anomaly.
