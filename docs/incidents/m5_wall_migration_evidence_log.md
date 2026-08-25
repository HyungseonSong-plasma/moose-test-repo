# M5 Wall Migration Diagnostic Evidence Log

**Status:** root cause localized to nonlinear convergence behavior  
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

The generic charged-transport path `phi -> E -> QPXFVElectrostaticDrift` is not the active failure mechanism. Mixture-averaged diffusion and bulk electrostatic drift remain out of scope unless new evidence contradicts this matrix.

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

- smoothing the hard gate does **not** restore conservation by itself;
- therefore hard active-set/Jacobian degeneracy is **not sufficient** to explain the incident;
- zero initial field still creates a distinct branch, but later convergence-probe evidence shows that the dominant conservation defect is premature nonlinear convergence.

## Earlier forced-iteration diagnostic — superseded interpretation

An earlier diagnostic reported only process PASS/FAIL for `nl_forced_its = 3` and was initially interpreted as evidence against insufficient nonlinear iterations. That interpretation is now superseded by the quantitative convergence probe below.

The important lesson is that process return code alone is not sufficient for this incident; the wall mass-balance closure must be measured numerically.

## Framework checks completed

The following MOOSE contracts have been inspected:

1. `FVFunctorNeumannBC::computeQpResidual()` evaluates its functor with `singleSidedFaceArg(), determineState()`.
2. `TransientInterface::determineState()` returns current state for implicit objects; implicit defaults to `true`.
3. `MooseVariableFV::evaluateGradient(FaceArg, state)` delegates to the FV face-gradient reconstruction.
4. On external Dirichlet boundaries, that reconstruction uses the boundary Dirichlet value and adjacent cell value at the requested state.
5. `SideFVFluxBCIntegral` evaluates the same `FVFluxBC::computeQpResidual()` when reporting the flux.
6. `FunctorMaterial::addFunctorProperty` defaults to `EXEC_ALWAYS`, so the wall functor itself is not intentionally cached across nonlinear iterations.

These checks reject or weaken simple old-state/caching explanations.

## Initial-potential amplitude sweep — executed

All cases solved the same final electrostatic problem:

```text
phi(0) = 20000 V
phi(1) = 0 V
```

Only the initial potential field changed:

```text
phi_IC(x) = s * 20000 * (1-x)
```

Executed result:

| `s` | Solve | `-dm/dt` | Left migration | Right migration `G_end` | Closure `C=(-dm/dt)/G_end` | Balance error | `phi_min` | `phi_max` |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|
| 0.00 | PASS | `-0.000000e+00` | `0` | `2.000000e-04` | `-0.000000` | `1.000000e+00` | `1.000000e+02` | `1.990000e+04` |
| 0.25 | PASS | `1.904762e-04` | `0` | `1.619048e-04` | `1.176471` | `1.500000e-01` | `1.000000e+02` | `1.990000e+04` |
| 0.50 | PASS | `1.818182e-04` | `0` | `1.636364e-04` | `1.111111` | `1.000000e-01` | `1.000000e+02` | `1.990000e+04` |
| 0.75 | PASS | `1.739130e-04` | `0` | `1.652174e-04` | `1.052632` | `5.000000e-02` | `1.000000e+02` | `1.990000e+04` |
| 1.00 | PASS | `1.666667e-04` | `0` | `1.666667e-04` | `1.000000` | `1.918604e-12` | `1.000000e+02` | `1.990000e+04` |

The final solved potential is identical across the sweep, so the conservation defect is not caused by different converged electrostatic states.

### One-Newton signature

For this 1D case:

```text
mu_i   = 0.01 m^2/(V s)
E_*    = 20000 V/m
dt     = 1e-5 s
dx     = 0.01 m
lambda = mu_i * E_* * dt / dx = 0.2
```

For every nonzero initial-field amplitude, the measured closure is exactly reproduced by a single Newton linearization of the bilinear wall term `w * E` around `E_0 = s E_*`:

```text
C(s) = 5 / (4 + s)
```

which predicts:

```text
s=0.25 -> 1.1764706
s=0.50 -> 1.1111111
s=0.75 -> 1.0526316
s=1.00 -> 1.0000000
```

matching the measured sweep values to output precision.

At `s=0`, the hard outward gate is initially inactive, producing the separate zero-update branch.

This establishes a strong one-Newton/truncated-nonlinear-closure signature.

## Quantitative convergence probe — decisive result

A follow-up first-timestep probe compared default convergence, minimum forced nonlinear iterations, and effectively disabled relative convergence.

| Case | `s` | Mode | Solve | `-dm/dt` | `G_end` | Closure `C` | Balance error |
|---|---:|---|:---:|---:|---:|---:|---:|
| `s100_default` | 1.00 | default | PASS | `1.666667e-04` | `1.666667e-04` | `1.000000` | `1.918604e-12` |
| `s050_default` | 0.50 | default | PASS | `1.818182e-04` | `1.636364e-04` | `1.111111` | `1.000000e-01` |
| `s050_forced2` | 0.50 | `nl_forced_its=2` | PASS | `1.666667e-04` | `1.666667e-04` | `1.000000` | `1.918604e-12` |
| `s050_forced3` | 0.50 | `nl_forced_its=3` | FAIL | n/a | n/a | n/a | n/a |
| `s050_abs_only` | 0.50 | `nl_rel_tol=1e-16` | PASS | `1.666667e-04` | `1.666667e-04` | `1.000000` | `1.918604e-12` |
| `s000_default` | 0.00 | default | PASS | `-0.000000e+00` | `2.000000e-04` | `-0.000000` | `1.000000e+00` |
| `s000_forced2` | 0.00 | `nl_forced_its=2` | PASS | `1.666667e-04` | `1.666667e-04` | `1.000000` | `1.918604e-12` |
| `s000_forced3` | 0.00 | `nl_forced_its=3` | PASS | `1.666667e-04` | `1.666667e-04` | `1.000000` | `1.918604e-12` |
| `s000_abs_only` | 0.00 | `nl_rel_tol=1e-16` | PASS | `1.666667e-04` | `1.666667e-04` | `1.000000` | `1.918604e-12` |

### Root-cause conclusion

The conservation defect is restored in both the partial-field and zero-field cases by either:

```text
A. requiring at least two nonlinear iterations
or
B. tightening nl_rel_tol sufficiently that the second nonlinear correction is executed
```

Therefore the dominant root cause is:

> **premature global nonlinear convergence after the first Newton correction.**

The electrostatic residual dominates the initial global reference norm. After the first Newton update solves the Laplace field, the global residual can satisfy the default relative criterion even though the wall species equation still contains the second-order/bilinear correction associated with the updated `w * E` wall flux. The timestep is then accepted with a species-wall residual that has not reached conservation closure.

The zero-field hard gate explains why `s=0` has a more extreme first-iteration signature, but it is not the dominant root cause because both `forced2` and tight relative convergence fully recover the same conservative solution.

The isolated `s050_forced3` process failure is **not yet interpreted** without its nonlinear log. It is not evidence against the root-cause conclusion because `forced2` and tight-relative-tolerance independently recover the identical conservative state.

## Corrective direction

Do not modify mixture diffusion, bulk electrostatic drift, or wall migration physics to fix this incident.

The corrective action belongs in nonlinear convergence control for coupled algebraic-potential/species solves. Candidate permanent approaches must ensure that the species residual cannot be hidden by the much larger initial electrostatic residual. Possible approaches to validate include:

1. variable/reference residual convergence for `w_O2_plus` and `phi` separately;
2. a convergence object with per-variable residual gates;
3. a documented minimum of two nonlinear iterations only as a temporary regression safeguard, not as the preferred general solution;
4. global tolerance/scaling changes only if they are shown robust across mesh, timestep, and physical parameter changes.

## Investigation hold points

Do not advance these layers until a robust convergence-control fix is selected and the zero-IC regression is promoted to canonical:

- reactor-scale O2+ integration;
- electron bulk drift;
- ion/electron dielectric surface-current accumulation;
- secondary electron emission.

## Evidence discipline

- Process-level PASS is not equivalent to physics/conservation PASS.
- Preserve the wall mass-balance gate at `1e-8` or tighter.
- Do not classify `s050_forced3` without its solver log.
- Do not hide this incident by changing physical coefficients or arbitrary timestep reduction.
