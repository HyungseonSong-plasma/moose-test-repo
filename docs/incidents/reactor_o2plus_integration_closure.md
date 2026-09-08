# Reactor-Scale O2+ Charged-Heavy Integration — Closure Record

**Status:** CLOSED  
**Work ID:** `reactor-o2plus-integration`  
**Complexity:** C3

## Scope closed

This work promoted the M5-validated solved-potential O2+ transport from the 1D reference into a 2D charged-heavy integration and resolved the previously open heavy-mixture electromigration-correction and self-consistent Poisson coupling gaps.

Validated capabilities:

- 2D x/y electrostatic bulk-drift orientation;
- 2D wall migration normal/clamp behavior;
- zero-potential-IC species-aware nonlinear convergence;
- O2+ inventory/wall-flux conservation;
- coexistence with the existing mixture-averaged and thermal-diffusion heavy transport;
- conservative heavy-mixture electromigration correction;
- AD species -> charge density -> Poisson source coupling;
- fully coupled 2D species <-> Poisson <-> electrostatic-drift solve.

Electron bulk drift, dielectric surface-current accumulation, and secondary electron emission remain separate later work items.

## Round-1 result

The first valid 2D integration batch returned:

```text
DECISION
ROUND1_PASS
```

This rejected the initial defects covering 2D drift orientation, wall normal/clamp, ReferenceResidualConvergence robustness, and conflict with the existing mixture/thermal heavy transport.

## Heavy-mass electromigration correction

A new FV flux kernel was implemented locally in QPX:

```text
QPXFVHeavyMassElectromigrationCorrection
```

It reconstructs the provisional direct charged-heavy migration mass flux face-by-face using the same electric-field, mobility, density, and upwind contract as `QPXFVElectrostaticDrift`, then distributes the negative total migration mass flux across every heavy-species equation according to the donor-cell heavy mass fractions.

The intended discrete invariant is:

```text
sum_k j_k,EM = 0
```

for a complete heavy-species mass-fraction set satisfying `sum_k w_k = 1`.

Validation A/B signature:

```text
correction_off  PASS  sum_err = 1.957e-02
correction_on   PASS  sum_err = 0.000e+00
```

The negative control demonstrates that direct ion drift alone breaks the local heavy mass-fraction closure. The correction restores the closure to reported precision without changing total ion or neutral inventory in the closed-domain test.

## Self-consistent Poisson coupling

No new QPX Poisson source kernel was required. The existing `QPXPlasmaChargeDensityMaterial` exposes the AD functor:

```text
poisson_charge_source = rho_q / epsilon_0
```

MOOSE `FVCoupledForce` consumes the AD functor directly in the FV potential residual. The production coupling path is therefore:

```text
species mass fractions
  -> QPXPlasmaChargeDensityMaterial
  -> poisson_charge_source
  -> FVCoupledForce
  -> phi
  -> QPXFVElectrostaticDrift
```

The fully coupled 2D test passed:

```text
self_consistent_2d PASS
ion_mass       = 0.000e+00 relative error
neutral_mass   = 0.000e+00 relative error
sum_w_err      = 0.000e+00
centroid_shift = -2.986e-04
phi_max        = 2.237e+01
```

This validates the nonlinear species <-> charge <-> potential <-> drift loop for the tested regime.

## Analytic Poisson validation and residual floor

The isolated analytic Poisson test initially used `nl_abs_tol = 1e-12` and failed to solve. A targeted tolerance probe gave:

```text
poisson_abs3e12 FAIL
poisson_abs1e10 PASS

w_err       = 0.000e+00
phi_max     = 4.257699e+01
phi_max exact = 4.256254e+01
phi_max rel error = 3.394e-04
phi_avg     = 2.839034e+01
phi_avg exact = 2.837503e+01
phi_avg rel error = 5.393e-04
```

Therefore the analytic formulation is validated. The isolated FV Poisson harness requires a floor-safe absolute tolerance of `1e-10` in this configuration. This is consistent with the previously established rule that algebraic FV potential solves must not demand convergence below their numerical residual floor.

The production conclusion is not that every coupled case should use `1e-10`; it is that the standalone analytic regression must use a tolerance above its measured residual floor while retaining its analytic error gates.

## Canonical promotion policy

Permanent regressions should preserve:

- conservative heavy-mass correction enabled;
- analytic Poisson with `nl_abs_tol = 1e-10` and analytic solution-error gates;
- full 2D self-consistent species/Poisson coupling.

The correction-disabled case remains a diagnostic negative control and must not be treated as a canonical success condition.

## Validator metrics

This is the first C3 work instrumented from work start through closure.

```text
WCC   = 9
T-WCC = 7
EVR   = 5
DBR   = 1
RWR   = 3
CLR   = 0
FBR   = yes
Reopened = no
```

### EVR reconstruction

1. first Round-1 bundle stopped on a boundary-restriction harness error;
2. corrected Round-1 bundle returned `ROUND1_PASS`;
3. implementation validation stopped on a reserved FunctionParser symbol in `self_consistent_2d`;
4. corrected implementation validation passed correction and self-consistent cases but exposed the isolated analytic-Poisson convergence-floor issue;
5. targeted Poisson residual-floor probe passed at `nl_abs_tol = 1e-10`.

### RWR reconstruction

Three avoidable test-delivery defects were recorded:

1. one multi-boundary FVBC was referenced by single-boundary `SideFVFluxBCIntegral` objects;
2. reserved FunctionParser symbol `x` was used as a user functor symbol;
3. the analytic Poisson test reused an absolute tolerance below the already-known algebraic FV residual-floor rule.

## Process result

Compared with the M5 C3 baseline:

```text
M5:                  DBR=5, FBR=no
reactor-o2plus:       DBR=1, FBR=yes
```

The parallel-hypothesis strategy substantially improved diagnostic efficiency. The remaining interaction cost was dominated by test-harness quality rather than hypothesis sequencing.

The next process target is therefore:

```text
preserve DBR <= 1 when feasible
RWR -> 0
pre-delivery static validation must include:
  - FVBC/postprocessor boundary-restriction compatibility
  - ParsedFunction/ParsedMaterial reserved-symbol checks
  - known residual-floor rules for algebraic FV solves
```
