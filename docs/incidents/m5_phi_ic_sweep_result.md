# M5 Wall Migration — phi-IC Sweep Result

**Status:** executed  
**Date:** 2026-08-25  
**Scope:** wall-only solved-potential migration, first timestep

## Measured sweep

| s | Solve | -dm/dt | Left migration | Right migration | G_end | C=(-dm/dt)/G_end | balance error | phi_min | phi_max |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.00 | PASS | -0.000000e+00 | 0.000000e+00 | 2.000000e-04 | 2.000000e-04 | -0.000000 | 1.000000e+00 | 1.000000e+02 | 1.990000e+04 |
| 0.25 | PASS | 1.904762e-04 | 0.000000e+00 | 1.619048e-04 | 1.619048e-04 | 1.176471 | 1.500000e-01 | 1.000000e+02 | 1.990000e+04 |
| 0.50 | PASS | 1.818182e-04 | 0.000000e+00 | 1.636364e-04 | 1.636364e-04 | 1.111111 | 1.000000e-01 | 1.000000e+02 | 1.990000e+04 |
| 0.75 | PASS | 1.739130e-04 | 0.000000e+00 | 1.652174e-04 | 1.652174e-04 | 1.052632 | 5.000000e-02 | 1.000000e+02 | 1.990000e+04 |
| 1.00 | PASS | 1.666667e-04 | 0.000000e+00 | 1.666667e-04 | 1.666667e-04 | 1.000000 | 1.918604e-12 | 1.000000e+02 | 1.990000e+04 |

Raw analyzer trend output:

```text
C(s) intercept = 4.928105e-01
C(s) slope     = 7.504644e-01
C(s) R^2       = 3.669727e-01
range(C)       = 1.176471e+00
```

## Pre-registered classification

The five-point sequence is not globally monotonic because s=0 follows a separate zero-field branch. Under the pre-registered decision table this is formally:

```text
CLASS = I_MIXED_NON_MONOTONIC
```

The pattern is nevertheless highly structured and should not be treated as random numerical noise.

## Exact one-Newton signature for s > 0

For this 1D test,

```text
lambda = mu_i * E_final * dt / dx
       = 0.01 * 20000 * 1e-5 / 0.01
       = 0.2
```

Linearizing the bilinear wall term w*E once about

```text
w = w0
E = s * E_final
```

while the linear electrostatic solve updates E to E_final gives

```text
w1/w0 = (1 - lambda + lambda*s) / (1 + lambda*s)
      = (4 + s) / (5 + s)
```

and therefore

```text
(-dm/dt) = 2e-4 * 5/(5+s)
G_end    = 2e-4 * (4+s)/(5+s)
C(s)     = 5/(4+s)
balance_error = (1-s)/5
```

These formulas reproduce the measured s=0.25, 0.50, 0.75, and 1.00 values to the printed precision.

This is strong evidence that the nonzero-IC cases are consistent with exactly one coupled Newton linearization of the wall migration product before the first timestep state is accepted. This is not yet a proof of the solver convergence reason; the nonlinear logs/convergence criteria must confirm why a further correction is not taken.

## Zero-field branch

At s=0, the hard outward gate is inactive at the initial state. The observed first-step inventory change is exactly zero while the timestep-end converged field produces a positive migration flux of 2e-4.

Therefore the current evidence supports two interacting mechanisms:

1. a zero-field hard-gate branch at exactly s=0;
2. a separate one-Newton/truncated nonlinear closure signature for every tested s>0.

The hard gate is therefore contributory at s=0 but is not sufficient to explain the broader nonzero-IC conservation defect.

## Next discriminating test

Compare the first-step closure for s=0.5 and s=0 under:

- default nonlinear convergence;
- nl_forced_its = 2;
- nl_forced_its = 3;
- effectively disabled relative convergence (nl_rel_tol = 1e-16, nl_abs_tol unchanged).

The goal is to determine whether the one-Newton signature is caused by early global convergence acceptance, and to reconcile the earlier binary forced-iteration FAIL result with numeric closure values.
