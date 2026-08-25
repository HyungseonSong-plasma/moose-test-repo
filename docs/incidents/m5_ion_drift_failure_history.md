# M5 Plasma Charge Core — Ion Drift Failure & Diagnostic History

**Status:** Investigation in progress  
**Scope:** prescribed-field O2+ drift -> solved-FV-potential-driven drift

## First failure

The last known-good baseline was the prescribed-field O2+ drift/wall regression. It passed global mass conservation, migration direction/clamp, positivity, and centroid shift.

The first failure appeared when the same 1D field was obtained from a solved FV potential instead of being prescribed directly:

```text
phi(0) = 20000 V
phi(1) = 0 V
E_x    = +2.0e4 V/m
dt     = 1e-5 s
```

First observed failure:

```text
Time Step 2, time = 2e-05, dt = 1e-05
Nonlinear solve did not converge due to DIVERGED_LINE_SEARCH iterations 3
Solve Did NOT Converge!
```

## Diagnostic history

| Step | Check/change | Result | Interpretation |
|---:|---|---|---|
| 1 | Initial `QPXFVElectrostaticDrift` using solved `phi` | FAIL | first bad transition |
| 2 | Align drift interpolation with framework FV advection pattern | FAIL | not a simple limiter/upwind contract issue |
| 3 | drift-kernel-only isolation | FAIL | solved-phi bulk path can reproduce failure |
| 4 | ion-wall-material-only isolation | FAIL | solved-phi wall path can reproduce failure |
| 5 | full JFNK | FAIL | not explained only by assembled Jacobian |
| 6 | replace reconstructed face gradient with direct normal potential difference | FAIL | reconstructed gradient not sole cause |
| 7 | solved-phi decoupled baseline; transport/wall returned to prescribed-field forms | FAIL | custom drift/wall objects are not required for original solver failure |
| 8 | pure FV `phi`: steady / transient zero-IC / transient exact-IC | PASS / FAIL / FAIL | repeated algebraic `phi` solve isolated |
| 9 | inspect variable residual history | root cause found | pure-`phi` transient failure is a residual-floor issue |
| 10 | raise pure-`phi` `nl_abs_tol` above measured floor | PASS | pure-`phi` incident closed |
| 11 | coupled solved-phi ion revalidation | FAIL physics gates | secondary issue exposed |
| 12 | reduce coupled `nl_abs_tol` from `1e-11` to `3e-12` | same FAIL | loose global tolerance is not the secondary root cause |
| 13 | conservation identity on first step | localized | transient inventory includes surface loss but misses migration contribution seen at timestep end |
| 14 | migration-state diagnostic with exact initial `phi` | at least full exact-phi case PASS | migration formulation can conserve when valid field state is available at start |

## Closed sub-incident: pure algebraic FV potential residual floor

Observed residual history:

```text
Time Step 1
phi residual: 1.33333e4
phi residual: 5.4149e-12
Solve Converged

Time Step 2
phi residual: 5.4149e-12
              2.43018e-12
              1.98800e-12
              1.98607e-12
DIVERGED_LINE_SEARCH
```

With:

```text
nl_abs_tol = 1e-12
nl_rel_tol = 1e-10
```

the measured numerical residual floor was about:

```text
R_floor ~= 2e-12
```

The repeated transient algebraic solve therefore attempted to reduce an already-converged state below the residual floor and failed in line search.

Tolerance-only pure-phi regressions passed after moving the absolute tolerance above the measured floor.

Reusable lesson:

```text
large R0 -> tiny R -> relative PASS on first solve
already-small R0 -> residual floor on next transient solve
absolute tolerance below floor -> false DIVERGED_LINE_SEARCH
```

Check `nl_abs_tol` against the measured residual floor before changing physics or timestep.

## Secondary issue: migration residual participation

Coupled solved-potential regression produced:

```text
max Laplace-potential rel error       = 9.947598e-15
max prescribed-field reference error = 1.525116e-01
max global ion mass-balance error     = 5.186371e-01
max left migration mass flux          = 0
```

The first-step detailed values were:

```text
dm                    = -2.004284571830e-09
dt                    =  1.0e-05
total wall rate       =  4.163770423212e-04
right migration rate  =  2.159485851380e-04
```

Therefore:

```text
-dm/dt
= 2.004284571830e-04

wall - migration
= 2.004284571832e-04
```

This localizes the secondary failure:

```text
surface loss participates in the transient inventory update,
while migration is visible in the timestep-end wall diagnostic but is absent
from that first-step mass update.
```

## Current hypothesis

The wall migration closure depends on solved `phi` and an active-set condition equivalent to:

```text
z_i * E_n > 0
```

The original coupled input starts from `phi = 0`; a timestep-end diagnostic sees the converged Laplace field. The current investigation is determining whether migration is activated in the actual FV residual at the same nonlinear state used by the inventory update.

The exact-initial-potential diagnostic demonstrates that the migration formulation itself can pass conservation when a valid field is available at the start of the solve.

## Current hold points

Do not advance these layers until the isolated solved-potential ion-drift regression is closed:

```text
reactor O2+ drift integration
electron bulk drift
ion + electron dielectric surface-current accumulation
secondary electron emission
```

## Investigation rules

- Do not hide failures with arbitrary timestep reduction.
- Do not change physical coefficients to improve convergence.
- Measure residual floors before changing nonlinear tolerances.
- Preserve the known-good prescribed-field regression.
- Isolate one suspected mechanism at a time.
- Close the 1D regression before returning to reactor geometry.
