# Incident: Step-3 initial CSV row contaminates transient acceptance minima

**Incident ID:** `INC-STEP3-INITIAL-ROW-001`  
**Status:** OPEN  
**Associated work:** Issue #8 `Charged heavy-species mixture diffusion + Poisson coupling`  
**Failure class:** validation/analyzer aggregation/scheduling defect; transient runtime passed

## Symptom

The corrected Step-3B small-dt case completed both input checking and runtime successfully, but the acceptance analyzer reported:

```text
w_O_min=0
w_O2_min=0
rho_min=0
p_min=0
abs_drho_composition_max=1.028241985693e-01
drho_sum_error_max=0
finite=True
```

and rejected only:

```text
G4_density_positive
G5_pressure_positive
```

## Current interpretation

The simultaneous exact zeros in `p_min`, `rho_min`, `w_O_min`, and `w_O2_min`, together with a successful nonlinear transient run, bounded `w_O`, an active composition contribution to `rho_dot`, an exact chain-sum identity, and finite output, strongly indicate that the analyzer is taking minima over an initial CSV/postprocessor row that does not represent a completed physical time step.

This is especially suspicious because the constrained O2 mass fraction should not physically be zero in the same state in which the reported maximum O mass fraction is about 0.3.

Therefore the current H3B metric rejection must not be interpreted as a density/pressure physics failure until post-initial rows are inspected separately.

## Correct validation rule

Transient state acceptance metrics must be evaluated over completed physical time steps, excluding initialization/output rows that precede the first solved time step. The initial row should be reported separately rather than silently mixed into extrema over the transient trajectory.

For Step 3B, recompute the gates over rows with

```text
time > min(recorded time)
```

and separately print the initial-row values.

## Decision rule

- all post-initial gates pass -> H3B SUPPORTED; close this incident after the analyzer regression is retained;
- post-initial `p_min <= 0` or `rho_min <= 0` -> genuine physical/numerical state failure; inspect the offending time step;
- no post-initial rows exist -> harness/output scheduling failure.

## Prevention

For transient CSV validation, distinguish initialization records from completed-step records before applying positivity, boundedness, conservation, or extrema-based acceptance gates.
