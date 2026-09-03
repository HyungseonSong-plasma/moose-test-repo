# R3 electron-density scaling verification

This experiment originally tested whether the R3 electron blocker was caused by the numerical representation of a large dimensional electron density rather than by a general MOOSE FV defect. The real-QPX campaign returned `SCALING_CONFIRMED_FULL_R3_PASS`, so the same O(1) representation has now been promoted into the canonical `recipes/issue91_r3.py` construction.

The physical reference density is

```text
N_ref = 1e16 m^-3
n_e_phys = N_ref * n_hat
```

The solver unknown remains named `n_e` inside the staged inputs, but its semantics are `n_hat ~ O(1)`. A derived `n_e_physical` functor reconstructs dimensional density for heavy-transport coupling and for the existing physical acceptance postprocessors.

The bounded verification campaign is:

```text
N0  normalized electron-only E=0 time + diffusion
    -> verifies the O(1) constant-state residual floor
    -> runs one bounded AD-vs-FD Jacobian check

N1  canonical normalized full R3-E0
    -> heavy transport consumes n_e_physical
    -> existing #91 physical checker is unchanged

N2  canonical normalized full R3-Econst (0.01 V/m)
    -> same representation plus accepted prescribed drift field
    -> existing #91 physical checker is unchanged
```

After production promotion, this package no longer applies a second normalization on top of `build_r3_input`. It verifies that the canonical recipe itself retains the proven representation. `FVOrthogonalDiffusion` is not used as a remedy.

Run on the QPX machine from repository root:

```bash
python -m experiments.R3_electron_scaling_counterfactual.run \
  --qpx "$QPX_OPT" \
  --results-root "$PWD/r3_results"
```

Interpretation remains:

```text
SCALING_REJECTED_N0
  -> O(1) representation does not repair the electron-only path.

SCALING_CONFIRMED_R3_E0_FAIL
  -> electron-only scaling is clean but a full-R3 coupling remains.

SCALING_CONFIRMED_R3_ECONST_FAIL
  -> R3-E0 is restored but prescribed-field drift exposes a separate issue.

SCALING_R3_PASS_JACOBIAN_HOLD
  -> physical R3 checks pass, but the bounded normalized Jacobian diagnostic is not clean.

SCALING_CONFIRMED_FULL_R3_PASS
  -> canonical normalized R3 reproduces the verified full remedy behavior.
```
