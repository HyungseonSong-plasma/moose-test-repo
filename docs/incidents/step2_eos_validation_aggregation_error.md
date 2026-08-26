# Incident: Step-2 EOS validation aggregation error

**Incident ID:** `INC-VALIDATION-AGG-001`  
**Status:** OPEN  
**Associated work:** Issue #8 `Charged heavy-species mixture diffusion + Poisson coupling`  
**Failure class:** validation/analyzer defect; physics solve passed

## Symptom

The cold-cache Step-2 recovery batch produced:

```text
T1_H1_channel_eos_coupling cold check        PASS
T1_H1_channel_eos_coupling cold normal run   PASS

H1: REJECTED
wO=[1.000000e-01,1.000000e-01]
wO2=[9.000000e-01,9.000000e-01]
Mn_err=3.101e-15
EOS_err~=3.877e-05
```

while H2 passed.

## Root cause in the analyzer

The analyzer did not use the spatial average of density. It approximated it as

```python
rhoavg = 0.5 * (rho_min + rho_max)
```

and then compared this quantity against

```python
p_avg * Mn_avg / (R*T)
```

This is not a valid EOS identity check. In a nonuniform pressure field,

```text
0.5 * (min(rho) + max(rho))
```

is generally not equal to the domain average of `rho`.

Because `Mn` is spatially uniform in T1, the correct aggregate identity is

```text
avg(rho) = avg(p) * Mn / (R*T)
```

provided `avg(rho)` and `avg(p)` are computed by matching spatial-average postprocessors.

## Current interpretation

- T1 input construction passed.
- T1 nonlinear solve passed.
- `w_O`, constrained `w_O2`, and `Mn` satisfied their acceptance criteria.
- The only rejecting H1 metric was computed by an invalid aggregation method.
- Therefore the reported `H1: REJECTED` is invalid.
- H1 is reclassified as **INCONCLUSIVE pending corrected EOS metric**, not rejected.
- H2 remains **SUPPORTED**.

No transport coefficient, EOS formula, WCNSFV kernel, or nonlinear tolerance should be changed in response to this result.

## Corrected confirmation test

Repeat only T1 with an `ElementAverageFunctorPostprocessor` for `rho_mat`, then evaluate

```text
EOS_rel_error = |rho_avg - p_avg*Mn_avg/(R*T)| /
                max(|rho_avg|, |p_avg*Mn_avg/(R*T)|)
```

Acceptance:

```text
EOS_rel_error < 1e-10
```

plus the previously passed mass-fraction and mean-molar-mass checks.

## Prevention rule

Do not replace a domain average with a midpoint of extrema. When validating an integral/average identity, all compared quantities must use compatible aggregation operators over the same domain and weighting.

## Closure criteria

1. corrected T1 EOS-average confirmation passes;
2. H1 is reclassified using the corrected metric;
3. the corrected analyzer becomes the regression implementation.
