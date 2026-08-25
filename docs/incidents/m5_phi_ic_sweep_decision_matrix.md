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

## Required result table

Fill this table directly from the sweep output. Do not infer missing values.

| `s` | Solve | `-dm/dt` | Left migration | Right migration | Total migration `G_end` | Closure `C=(-dm/dt)/G_end` | `phi_min` | `phi_max` |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|
| 0.00 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 0.25 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 0.50 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 0.75 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 1.00 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

### Primary conservation gate

For a solved case define:

```text
balance_error = abs(dm + G_end*dt) / max(abs(dm), abs(G_end*dt), tiny)
```

Permanent conservation acceptance target:

```text
balance_error < 1e-8
```

Equivalently, when `G_end != 0`, `C` should be 1 within the same numerical tolerance.

## Validity checks before interpreting the sweep

The sweep is interpretable only if all of the following are true:

1. The same QPX executable/runtime is used for all five cases.
2. The same source variant is used for all five cases.
3. All non-IC input parameters are identical.
4. Final solved potential fields are mutually consistent across cases. Compare `phi_min` and `phi_max` across the five runs; large case-to-case variation invalidates a wall-only interpretation.
5. Left migration remains approximately zero and right migration remains positive for the chosen field direction.
6. If a case does not reach the first positive-time row, classify it as a solver/convergence branch before applying the closure-pattern table.

## Decision matrix

| Observed sweep pattern | Quantitative signature | Conclusion | Next action | Confidence |
|---|---|---|---|---|
| **A. Strong continuous IC dependence** | `C(s)` rises monotonically with `s`; approximately linear or otherwise strongly correlated with `s`; `C(1)` near 1 while low-`s` cases are far below 1; final `phi` is the same | Wall migration residual has genuine **initial/path-state dependence** even though the converged electrostatic solution is common | Instrument residual-time wall flux versus nonlinear iteration/state. Trace the value passed through `FVFunctorNeumannBC -> ion_migration_mass_flux -> potential.gradient`. Do not modify bulk drift | **High** |
| **B. Zero-only anomaly** | `s=0` fails conservation, while `s=0.25,0.50,0.75,1.0` all satisfy the `1e-8` gate | A special **zero-field initialization degeneracy** exists. Because smooth-gate zero-IC already failed, hard `max()` alone is insufficient | Inspect AD dependency registration / boundary-gradient evaluation specifically at zero field and zero initial potential. Compare derivative support at `s=0` and infinitesimal nonzero `s` | **High** |
| **C. Threshold behavior** | Low `s` cases fail, high `s` cases pass, with an abrupt transition rather than a smooth trend | A branch/threshold mechanism remains in the wall path; may involve active-set interaction but is not explained by the previously tested hard gate alone | Add finer sweep around the transition (`s` bracket) and record active branch, field normal, and derivative norm | **Medium-High** |
| **D. IC-independent failure** | All or most solved cases have nearly the same `C`, and `C` is materially different from 1; final `phi` is common | Initial potential is **not causal**. Focus on wall-flux residual/inventory accounting, boundary face contract, scaling/sign, or time-discretization consistency | Compare cell residual contribution from each wall BC against `SideFVFluxBCIntegral`; add a direct residual-accounting diagnostic | **High** |
| **E. All cases conserve** | All five cases satisfy `balance_error < 1e-8` | The sweep does not reproduce the incident | Stop physics interpretation. Reconcile executable, source patch state, input differences, `nl_forced_its`, checker version, and runtime environment against the failing case | **High** |
| **F. Exact (`s=1`) fails in sweep** | `s=1` fails although canonical `wall_only_exact_phi_ic` is PASS | The sweep configuration is not equivalent to the canonical exact-IC test; current sweep cannot be used to infer IC causality | Diff the two inputs line-by-line. In particular inspect `nl_forced_its`, end time, source variant, and wall-gate patch state | **High** |
| **G. Final phi differs materially by IC** | `phi_min`/`phi_max` or equivalent field diagnostics differ across cases beyond numerical noise | Electrostatic solve/path itself is not reaching a common final state | Diagnose phi solve/convergence first. Do not attribute wall balance differences to wall migration | **High** |
| **H. Directionality breaks** | Left migration becomes nonzero when it should be clamped, or right migration changes sign | Wall normal / FaceArg / directed-field construction is implicated | Inspect `outwardNormal(FaceArg)`, `face_side`, boundary orientation, and `E_n` sign before any state hypothesis | **High** |
| **I. Mixed/non-monotonic pattern** | No stable trend; some intermediate cases behave inconsistently while final phi is common | More than one mechanism or a numerical discontinuity is interacting | Preserve all logs. Repeat only anomalous amplitudes, then add per-iteration wall-flux instrumentation before changing physics | **Low-Medium** |

## Pre-registered trend metrics

For the five solved closure ratios `C(s)` compute:

- monotonicity of `C` with increasing `s`;
- linear fit `C = a + b s`;
- `R^2` of the fit;
- range `max(C)-min(C)`;
- final-potential spread across cases.

Use these only to support the decision table; they do not replace the conservation gate.

Suggested evidence thresholds for pattern classification:

```text
Strong continuous IC dependence:
    monotonic increasing
    AND R^2 >= 0.95 for C vs s
    AND |b| >= 0.2
    AND range(C) >= 0.2

IC-independent failure:
    range(C) <= 0.05
    AND mean(|C-1|) >= 0.05

Zero-only anomaly:
    s=0 fails conservation
    AND every s>=0.25 passes conservation
```

If a pattern sits near a threshold, classify it as mixed rather than forcing a conclusion.

## Evidence already established before this sweep

| Hypothesis | Status before sweep | Evidence |
|---|---|---|
| Generic solved-phi bulk drift failure | **Rejected** | bulk exact PASS + bulk zero PASS |
| Wall-path localization | **Supported** | wall exact PASS + wall zero FAIL |
| Hard active-set alone | **Rejected as sufficient cause** | smooth-gate zero-IC still FAIL |
| Too few nonlinear iterations | **Rejected** | hard/smooth with `nl_forced_its=3` both FAIL |
| Explicit old-state BC by design | **Weakened** | implicit `FVFunctorNeumannBC` uses `determineState()`; implicit defaults current |
| Intentional FunctorMaterial cache across nonlinear iterations | **Weakened** | `addFunctorProperty` defaults to `EXEC_ALWAYS` |

## Post-sweep action rule

Do not edit production wall physics immediately after the sweep. First:

1. classify the result using exactly one row above, or `Mixed` if no row fits;
2. append the numeric result table to `m5_wall_migration_evidence_log.md`;
3. record the selected conclusion and rejected alternatives;
4. only then create the next diagnostic or production patch.

When the zero-IC wall migration conservation defect is fixed, promote the zero-IC wall-only case and the corresponding full solved-phi regression from diagnostic to canonical.
