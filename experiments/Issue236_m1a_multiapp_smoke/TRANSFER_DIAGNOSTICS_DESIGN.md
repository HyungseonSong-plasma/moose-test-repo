# Issue 236 transfer/recovery diagnostics

This diagnostic layer is observational. It must not change the multirate
physics, timestep policy, nonlinear solver, chemistry-off state, surface
closure, or the existing operational `fast_from_electron` payload.

## Question

Run 31 ended with an accepted fast-child state whose electron density was
positive everywhere, followed by a parent heavy solve in which
`heavy_transport` observed a negative electron number density. The diagnostic
must localize the first bad value without relying on ambiguous floating-point
time joins across cutback/recovery attempts.

## Four parallel lanes

### A. Child accepted history

At `INITIAL TIMESTEP_END`, record min/max values on the plasma block for:

- `n_e`
- `n_epsilon`
- `potential_plasma`
- `n_e_physical`

Also record timestep number, failed-timestep count, and `dt`. `FAILED` output is
intentionally excluded so failed Newton/recovery states cannot masquerade as an
accepted child source.

### B. Parent immediately after the transfer event

The current run-31 contract is hard-audited:

- `MultiApps/electron execute_on = TIMESTEP_BEGIN`;
- operational `fast_from_electron` is `SAME_AS_MULTIAPP`/`TIMESTEP_BEGIN`;
- a diagnostic snapshot transfer also executes at `TIMESTEP_BEGIN`.

The diagnostic transfer copies the same child variables into dedicated parent
Aux snapshots:

- `issue236_diag_snap_ne`
- `issue236_diag_snap_nepsilon`
- `issue236_diag_snap_phi`

The parent lane then records both the operational mirrors and these snapshots in
the same CSV row. This removes the need to infer which child CSV row was the
source during timestep cutback/retry.

### C. Parent heavy nonlinear evaluations

At `NONLINEAR`, record the operational parent mirrors and the immutable snapshot
variables. A dedicated CSV with `new_row_detection_columns = all` preserves
multiple Newton evaluations at the same physical time.

Parent B/C rows are paired by the tuple

`(NumTimeSteps, NumFailedTimeSteps, dt, time)`

rather than by time alone.

### D. Exact heavy-transport electron input

Read `FunctorMaterials/heavy_transport/electron_number_density` from the built
parent input and instrument that exact functor in both B and C. This distinguishes
an otherwise healthy parent `n_e` from a stale/incorrect scaling or material
functor path.

## Interpretation

- child accepted state is positive, but B operational mirror differs from the
  same-event snapshot: operational transfer/target-state handling problem;
- B operational mirror and snapshot agree and are positive, but C operational
  state becomes negative while the snapshot stays positive: parent-side
  working-state/recovery mutation;
- B/C `n_e` is positive while D is negative: heavy transport functor/scaling or
  state-selection problem;
- B/C/D remain positive while the material reports a negative density: inspect
  the exact material evaluation/trial-state path;
- transfer chain remains healthy but fast solve still fails near the previous
  0.7 ns limit: move separately to sheath/wall-loss closure diagnostics.

## Non-invasiveness contract

The wrapper must preserve `dt_e = 1e-10 s`, the 100:1 schedule, chemistry-off
state, energy drift, wall losses, SEE, VI bounds, and the operational transfer.
It may add only diagnostic Aux snapshots, one diagnostic copy transfer,
postprocessors, CSV outputs, and artifact-side analysis. Diagnostic values do
not participate in the physics residual or acceptance gates.
