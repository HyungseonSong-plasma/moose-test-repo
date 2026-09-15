# Issue 236 transfer/recovery diagnostics

This diagnostic layer is intentionally observational. It must not change the
multirate physics, transfer payloads, nonlinear solver, timestep policy, or
surface closure.

## Question

Run 31 ended with an accepted fast-child state whose electron density was
positive everywhere, followed by a parent heavy solve in which
`heavy_transport` observed a negative electron number density. The diagnostic
must distinguish:

1. a stale/recovered value being selected on the child side;
2. a mismatch during `MultiAppCopyTransfer`;
3. a parent Aux/functor value changing after transfer but before/during the
   heavy nonlinear solve.

## Parallel observation lanes

### A. Child accepted state

At `INITIAL TIMESTEP_END`, record min/max values over the plasma block for:

- `n_e`
- `n_epsilon`
- `potential_plasma`
- `n_e_physical`

Also record the child timestep number and `dt`.

This lane represents accepted child states only. It deliberately does not use
`NONLINEAR` execution, so failed Newton trial values cannot be mistaken for
accepted transfer sources.

### B. Parent immediately after child-to-parent transfer

At `TIMESTEP_BEGIN`, record the same min/max values for the parent Aux mirrors
plus `n_e_physical`, together with parent timestep number and `dt`.

MOOSE executes FROM_MULTIAPP transfers after the source MultiApp on the shared
execution schedule, while UserObject-derived postprocessors on that schedule
execute after transfers. Therefore this lane samples after `fast_from_electron`
and before the heavy nonlinear solve.

### C. Parent heavy nonlinear evaluations

At `NONLINEAR`, record the same parent quantities. Use a dedicated CSV output
with `new_row_detection_columns = all` so multiple nonlinear evaluations at the
same physical time remain visible.

Interpretation:

- A positive, B negative: transfer/recovery source-selection problem.
- A and B agree, B positive, C negative: parent-side state/functor/nonlinear
  handling problem.
- `n_e` positive but `n_e_physical` negative in B or C: parent scaling/functor
  construction problem.

## Non-invasiveness contract

The diagnostic wrapper must:

- preserve `dt_e = 1e-10 s`, the 100:1 schedule, chemistry-off state, energy
  drift, wall losses, SEE, VI bounds, and existing transfers;
- add only postprocessors and CSV outputs;
- never modify the Issue-236 trigger file;
- fail self-test if any diagnostic lane or execution schedule is missing;
- emit separate diagnostic CSV files so existing acceptance CSV parsing is not
  perturbed.
