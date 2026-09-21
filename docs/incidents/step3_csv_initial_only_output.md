# Incident: Step-3 CSV contains only initial zero row

**Incident ID:** `INC-STEP3-CSV-001`  
**Status:** OPEN  
**Associated work:** Issue #8 `Charged heavy-species mixture diffusion + Poisson coupling`  
**Failure class:** validation/output capture; physics solve status not yet reclassified

## Symptom

The Step-3 transient H3B CSV contained only one row:

```text
time,...
0,0,0,...,0
```

Even though the runner reported `check=0 run=0` for the transient case.

## Immediate implication

- The existing H3B acceptance metrics are invalid because they were computed from an initialization/output placeholder row only.
- `rho_min=0` and `p_min=0` in that CSV do not prove a physical negative/zero-state failure.
- The previous `STEP3_H3B_METRIC_FAIL` decision is therefore not a valid physics decision.
- Because there are no post-initial rows in the supplied CSV, H3B remains **INCONCLUSIVE** until timestep-end output is captured.

## Relevant MOOSE output behavior

MOOSE output objects default to `execute_on = 'initial timestep_end'`, and the documentation recommends explicitly using `execute_on = 'timestep_end'` when the initial condition should be suppressed. The CSV object supports postprocessor execution control through `execute_postprocessors_on`.

Therefore the next diagnostic should explicitly force timestep-end CSV/postprocessor output and verify that the number of recorded physical rows matches the requested transient steps.

## Corrected validation gate

For each transient case:

1. run with explicit timestep-end CSV/postprocessor output;
2. require at least one `time > 0` row;
3. verify final recorded time against `num_steps * dt`;
4. only then apply positivity / `drho_dt` chain-rule acceptance metrics.

## Decision rule

- timestep-end rows present and all H3B gates pass -> `STEP3_PASS`;
- solver advances but CSV still has no `time > 0` rows -> output-capture defect remains;
- solver does not advance despite `run rc=0` -> inspect executioner/log termination condition;
- physical timestep rows contain nonpositive `p` or `rho` -> genuine transient-state failure.

## Closure criteria

Close after a corrected bundle records physical timestep rows and H3B is reclassified from those rows.
