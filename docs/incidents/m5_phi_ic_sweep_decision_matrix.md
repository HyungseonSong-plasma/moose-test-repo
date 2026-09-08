# M5 Wall Migration — Initial-Potential Sweep Decision Matrix

**Purpose:** classify the wall-migration failure from the five-case initial-potential sweep without changing the interpretation after seeing the data.

## Sweep invariant

Every case must solve the same final electrostatic problem:

```text
phi(0) = 20000 V
phi(1) = 0 V
```

Only the initial potential amplitude changes:

```text
phi_IC(x) = s * 20000 * (1-x)
s = 0.00, 0.25, 0.50, 0.75, 1.00
```

The wall-only ion transport setup, mobility, density, timestep, mesh, boundary conditions, and checker must otherwise remain identical.

## Executed result table

| `s` | Solve | `-dm/dt` | Left migration | Right migration | Total migration `G_end` | Closure `C=(-dm/dt)/G_end` | `phi_min` | `phi_max` |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|
| 0.00 | PASS | `-0.000000e+00` | `0` | `2.000000e-04` | `2.000000e-04` | `-0.000000` | `1.000000e+02` | `1.990000e+04` |
| 0.25 | PASS | `1.904762e-04` | `0` | `1.619048e-04` | `1.619048e-04` | `1.176471` | `1.000000e+02` | `1.990000e+04` |
| 0.50 | PASS | `1.818182e-04` | `0` | `1.636364e-04` | `1.636364e-04` | `1.111111` | `1.000000e+02` | `1.990000e+04` |
| 0.75 | PASS | `1.739130e-04` | `0` | `1.652174e-04` | `1.652174e-04` | `1.052632` | `1.000000e+02` | `1.990000e+04` |
| 1.00 | PASS | `1.666667e-04` | `0` | `1.666667e-04` | `1.666667e-04` | `1.000000` | `1.000000e+02` | `1.990000e+04` |

### Primary conservation gate

For a solved case define:

```text
balance_error = abs(dm + G_end*dt) / max(abs(dm), abs(G_end*dt), tiny)
```

Permanent conservation acceptance target:

```text
balance_error < 1e-8
```

The executed balance errors were:

```text
s=0.00 -> 1.000000e+00
s=0.25 -> 1.500000e-01
s=0.50 -> 1.000000e-01
s=0.75 -> 5.000000e-02
s=1.00 -> 1.918604e-12
```

Only the exact-initial-potential case satisfied the conservation gate under the default nonlinear convergence settings.

## Validity checks

All sweep validity checks passed:

1. same executable/runtime;
2. same source variant;
3. only initial phi amplitude varied;
4. final `phi_min` and `phi_max` identical across all five cases;
5. left migration zero and right migration positive in every case;
6. all cases reached the first positive-time state.

Therefore the sweep is physically interpretable.

## Pre-registered decision matrix

| Observed sweep pattern | Quantitative signature | Conclusion | Next action | Confidence |
|---|---|---|---|---|
| **A. Strong continuous IC dependence** | `C(s)` rises monotonically with `s`; approximately linear or otherwise strongly correlated with `s`; `C(1)` near 1 while low-`s` cases are far below 1; final `phi` is the same | Wall migration residual has genuine **initial/path-state dependence** even though the converged electrostatic solution is common | Instrument residual-time wall flux versus nonlinear iteration/state | **High** |
| **B. Zero-only anomaly** | `s=0` fails conservation, while `s=0.25,0.50,0.75,1.0` all satisfy the gate | Special zero-field initialization degeneracy | Inspect zero-field derivative support | **High** |
| **C. Threshold behavior** | Low `s` cases fail, high `s` cases pass, with abrupt transition | Branch/threshold mechanism | Finer sweep around transition | **Medium-High** |
| **D. IC-independent failure** | All or most solved cases have nearly the same `C != 1` | Initial phi not causal | Residual/inventory accounting | **High** |
| **E. All cases conserve** | All five pass | Incident not reproduced | Reconcile runtime/input/source identity | **High** |
| **F. Exact (`s=1`) fails** | Exact sweep case fails although canonical exact case passes | Sweep not equivalent to canonical | Diff inputs | **High** |
| **G. Final phi differs** | Final potential diagnostics differ | Electrostatic solve/path not common | Diagnose phi solve first | **High** |
| **H. Directionality breaks** | Wrong left/right migration sign | Wall normal / FaceArg implicated | Inspect normal and directed field | **High** |
| **I. Mixed/non-monotonic pattern** | No pre-registered single trend fits | More than one mechanism or numerical discontinuity | Preserve logs and add discriminating diagnostic | **Low-Medium** |

## Sweep-only classification

Using only the pre-registered linear trend classifier, the executed sweep falls under:

```text
I. Mixed/non-monotonic pattern
```

because `s=0` is a distinct hard-gate branch and the remaining nonzero-amplitude closure curve is nonlinear rather than fitting the pre-registered linear trend threshold.

However, the numeric values show additional exact structure that was not part of the pre-registration.

## Post-sweep exact structure

For this test:

```text
lambda = mu_i * E_* * dt / dx = 0.2
```

For every `s > 0`, a single Newton linearization of the bilinear wall term `w*E` predicts:

```text
C(s) = 5 / (4 + s)
```

which gives:

```text
s=0.25 -> 1.1764706
s=0.50 -> 1.1111111
s=0.75 -> 1.0526316
s=1.00 -> 1.0000000
```

These predictions match the measured values to output precision.

At `s=0`, the hard outward gate is initially inactive, so the first update contains no migration contribution.

This means the sweep contains two visible signatures:

1. zero-field hard-gate branch at `s=0`;
2. one-Newton/truncated nonlinear closure for `s>0`.

## Convergence-probe resolution

The follow-up quantitative convergence probe resolved the ambiguous `I` classification:

```text
s=0.5 default       -> C=1.111111, balance error=1e-1
s=0.5 forced2       -> C=1.000000, balance error=1.918604e-12
s=0.5 nl_rel=1e-16 -> C=1.000000, balance error=1.918604e-12

s=0.0 default       -> C=0.000000, balance error=1
s=0.0 forced2       -> C=1.000000, balance error=1.918604e-12
s=0.0 nl_rel=1e-16 -> C=1.000000, balance error=1.918604e-12
```

Therefore the dominant root cause is not wall physics or a permanently stale state. It is:

> **premature global nonlinear convergence after the first Newton correction.**

The initial electrostatic residual is sufficiently large that the global relative convergence criterion can be satisfied after the first field correction even though the species-wall equation still requires a second nonlinear correction. Requiring two nonlinear iterations or tightening relative convergence fully restores conservation.

The zero-field active-set branch amplifies the first-iteration error at `s=0`, but it is not the dominant root cause because the same conservative state is recovered without changing wall physics.

## Updated hypothesis status

| Hypothesis | Current status | Evidence |
|---|---|---|
| Generic solved-phi bulk drift failure | **Rejected** | bulk exact PASS + bulk zero PASS |
| Wall-path localization | **Supported as symptom location** | wall exact PASS + wall zero FAIL under default convergence |
| Hard active-set alone | **Rejected as root cause** | smoothing alone fails; forced2/tight tolerance fix without changing physics |
| Too few nonlinear corrections under default convergence | **Confirmed** | forced2 and tight `nl_rel_tol` both restore exact conservation |
| Explicit old-state BC by design | **Rejected/unsupported** | current-state MOOSE contracts + convergence recovery |
| Intentional functor cache | **Rejected/unsupported** | `EXEC_ALWAYS` + convergence recovery |
| Different final electrostatic solution by IC | **Rejected** | identical final `phi_min/phi_max` across sweep |

## Next-action rule

Do not patch wall migration physics for this incident.

The next validation must compare robust convergence-control strategies that prevent the species residual from being hidden by the initially dominant electrostatic residual. A minimum-two-iteration rule may be used as a diagnostic/regression safeguard, but the preferred production solution should use a convergence criterion that explicitly protects the coupled species residual.

The isolated `s050_forced3` solver failure remains a separate unclassified observation until its nonlinear log is inspected; it does not overturn the root-cause result because `forced2` and tight relative tolerance independently recover the same conservative state.
