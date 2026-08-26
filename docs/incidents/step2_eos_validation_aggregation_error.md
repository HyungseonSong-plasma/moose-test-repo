# Incident: Step-2 EOS validation aggregation error

**Incident ID:** `INC-VALIDATION-AGG-001`  
**Status:** CLOSED  
**Associated work:** Issue #8 `Charged heavy-species mixture diffusion + Poisson coupling`  
**Failure class:** validation/analyzer defect; physics solve passed

## Symptom

The cold-cache Step-2 recovery batch produced a false rejection:

```text
T1_H1_channel_eos_coupling cold check        PASS
T1_H1_channel_eos_coupling cold normal run   PASS

H1: REJECTED
Mn_err=3.101e-15
EOS_err~=3.877e-05
```

while H2 passed.

## Root cause

The analyzer approximated the spatial average of density as

```python
rhoavg = 0.5 * (rho_min + rho_max)
```

and compared that quantity against

```python
p_avg * Mn_avg / (R*T)
```

This is not a valid EOS identity check in a nonuniform pressure field. A midpoint of extrema is not a domain average.

Because `Mn` is spatially uniform in T1, the correct aggregate identity is

```text
avg(rho) = avg(p) * Mn / (R*T)
```

with matching spatial-average operators.

## Corrected regression

The corrected T1 confirmation added an `ElementAverageFunctorPostprocessor` for `rho_mat` and evaluated

```text
EOS_rel_error = |rho_avg - p_avg*Mn_avg/(R*T)| /
                max(|rho_avg|, |p_avg*Mn_avg/(R*T)|)
```

Observed result:

```text
CHECK: PASS
RUN: PASS

wO=[1.000000000e-01,1.000000000e-01]
wO2=[9.000000000e-01,9.000000000e-01]
Mn_avg=2.909090909091e-02
Mn_rel_error=3.101e-15
p_avg=1.348284291773e+00
rho_avg=1.572473474343e-05
p_avg*Mn_avg/(R*T)=1.572473474343e-05
EOS_rel_error=2.198e-14

H1: SUPPORTED
H2: SUPPORTED
DECISION
STEP2_PASS
```

Acceptance `EOS_rel_error < 1e-10` is satisfied by more than three orders of magnitude.

## Final disposition

- H1 composition/EOS-to-WCNS coupling: **SUPPORTED**.
- H2 QPX mass-fraction advection + mixture-averaged diffusion on the same closure: **SUPPORTED**.
- Step 2 is complete.
- No physics coefficient, EOS formula, WCNSFV kernel, or nonlinear tolerance change was required.

## Reusable prevention rule

Do not replace a domain average with a midpoint of extrema. When validating an integral/average identity, all compared quantities must use compatible aggregation operators over the same domain and weighting.

This incident is eligible for promotion to the troubleshooting index because the root cause was isolated, the analyzer was corrected, and the corrected regression passed.
