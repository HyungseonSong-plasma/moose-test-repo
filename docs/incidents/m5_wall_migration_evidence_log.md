# M5 Wall Migration Diagnostic Evidence Log

**Status:** investigation in progress  
**Scope:** solved-FV-potential-driven O2+ wall migration only  
**Canonical parent incident:** `docs/incidents/m5_ion_drift_failure_history.md`

## Established baseline

The canonical exact-potential regressions remain PASS:

| Test | Type | Result | Meaning |
|---|---|---:|---|
| `full_exact_phi_ic` | canonical | PASS | full solved-phi drift/wall path works when a valid field exists initially |
| `migration_only_exact_phi_ic` | canonical | PASS | wall migration formulation can conserve with exact initial phi |

## Executed localization matrix

| Case | Bulk drift | Wall migration | Initial phi | Result | Interpretation |
|---|---:|---:|---|---:|---|
| `bulk_only_exact_phi_ic` | ON | OFF | exact | PASS | bulk solved-phi drift healthy |
| `bulk_only_zero_phi_ic` | ON | OFF | zero | PASS | bulk solved-phi drift healthy even from zero phi |
| `wall_only_exact_phi_ic` | OFF | ON | exact | PASS | wall closure can conserve |
| `wall_only_zero_phi_ic` | OFF | ON | zero | FAIL | failure localized to wall path + zero initial phi |
| `migration_only_zero_phi_ic` | existing bridge case | wall active | zero | FAIL | agrees with wall-only localization |

### Localization conclusion

The generic charged-transport path `phi -> E -> QPXFVElectrostaticDrift` is not the active failure mechanism. Mixture-averaged diffusion and bulk electrostatic drift are out of scope unless new evidence contradicts this matrix.

## Hard active-set diagnostic

`QPXIonWallFluxMaterial` implements outward migration using a hard gate equivalent to:

```text
max(z_i * E_n, 0)
```

A diagnostic regularization was introduced only for testing:

```text
f(x) = 0.5 * x * (1 + tanh(x / eps))
```

with `f(0)=0` and `f'(0)=0.5`.

Observed first-step result:

```text
dt                                  = 1.000000000000e-05
dm                                  = -9.999999999999e-10
left migration loss rate            = 0.000000000000e+00
right migration loss rate           = 1.800000000000e-04
expected dm                         = -1.800000000000e-09
migration balance relative error    = 4.444444e-01
OVERALL: FAIL
```

Interpretation:

- smoothing the hard gate does **not** restore conservation;
- therefore hard active-set/Jacobian degeneracy is **not sufficient** to explain the incident;
- the numerical value `-dm/dt = 1.0e-4` is consistent with the first linearization scale of the smoothed gate, but this observation alone does not establish the final mechanism.

## Forced nonlinear-iteration diagnostic

Two zero-phi wall-only cases were run with `nl_forced_its = 3`:

| Case | Gate | Forced nonlinear iterations | Result |
|---|---|---:|---:|
| `hard_gate_forced3` | hard | 3 | FAIL |
| `smooth_gate_forced3` | smooth | 3 | FAIL |

Interpretation:

- insufficient nonlinear iteration count is **not** the root cause;
- simply forcing additional nonlinear residual/Jacobian rebuilds does not close the wall migration balance;
- hard-gate smoothing plus extra nonlinear iterations still fails.

## Framework checks completed

The following MOOSE contracts have been inspected:

1. `FVFunctorNeumannBC::computeQpResidual()` evaluates its functor with `singleSidedFaceArg(), determineState()`.
2. `TransientInterface::determineState()` returns current state for implicit objects; implicit defaults to `true`.
3. `MooseVariableFV::evaluateGradient(FaceArg, state)` delegates to the FV face-gradient reconstruction.
4. On external Dirichlet boundaries, that reconstruction uses the boundary Dirichlet value and adjacent cell value at the requested state.
5. `SideFVFluxBCIntegral` evaluates the same `FVFluxBC::computeQpResidual()` when reporting the flux.
6. `FunctorMaterial::addFunctorProperty` defaults to `EXEC_ALWAYS`, so the wall functor itself is not intentionally cached across nonlinear iterations.

These checks weaken the simple explanations that the BC is explicitly old-state, that the boundary gradient is inherently old-state, or that the functor is intentionally cached.

## Current discriminating experiment: initial-phi amplitude sweep

All cases solve the same final Laplace problem:

```text
phi(0) = 20000 V
phi(1) = 0 V
```

Only the initial potential field differs:

```text
phi_IC(x) = s * 20000 * (1-x)
```

with:

```text
s = 0.00, 0.25, 0.50, 0.75, 1.00
```

For every case record the first positive-time row:

- `-dm/dt`
- left migration rate
- right migration rate
- total final migration rate
- closure ratio `C = (-dm/dt) / Gamma_migration,end`
- `phi_min`, `phi_max`
- solver status
- nonlinear residual history if the case fails or behaves anomalously

The sweep decision table is maintained in:

`docs/incidents/m5_phi_ic_sweep_decision_matrix.md`

## Investigation hold points

Do not change or advance the following while this incident is open:

- mixture-averaged diffusion physics;
- bulk `QPXFVElectrostaticDrift` implementation;
- reactor-scale O2+ integration;
- electron bulk drift;
- ion/electron dielectric surface-current accumulation;
- secondary electron emission.

## Evidence discipline

- A diagnostic FAIL is evidence only for the mechanism isolated by that test.
- Do not promote a diagnostic to canonical until the failure is fixed and the expected behavior becomes a permanent invariant.
- Do not classify infrastructure/runtime failures as physics failures.
- Preserve exact numeric outputs whenever they are used to reject a hypothesis.
