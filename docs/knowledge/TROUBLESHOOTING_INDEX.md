# Troubleshooting Index

This index maps recurring symptoms to incident records and minimal regression cases.

| Symptom / keyword | First reference | Status |
|---|---|---|
| `DIVERGED_LINE_SEARCH` on repeated transient solve of algebraic FV potential | `docs/incidents/m5_ion_drift_failure_history.md` | residual-floor mechanism CLOSED for pure `phi` case |
| Solved-potential ion drift differs from prescribed-field reference | `docs/incidents/m5_ion_drift_failure_history.md` | investigation in progress |
| Wall migration postprocessor is nonzero but transient inventory does not include the same loss | `tests/m5_plasma_charge/ion_wall_migration_state/` | isolated diagnostic cases |

## Reusable pattern: algebraic variable inside a transient solve

Observed pattern:

```text
Time Step n:
large initial residual -> tiny residual -> relative convergence PASS

Time Step n+1:
already-small initial residual -> numerical residual floor
-> absolute tolerance below floor
-> line-search failure
```

First diagnostic:

```text
compare nl_abs_tol with measured residual floor
```

Do not modify physics coefficients or timestep before checking this condition.

## Incident promotion rule

An incident can be promoted from `docs/incidents/` to reusable knowledge only after:

1. root cause is isolated,
2. fix is verified,
3. regression gate passes,
4. scope/limitations are documented.
