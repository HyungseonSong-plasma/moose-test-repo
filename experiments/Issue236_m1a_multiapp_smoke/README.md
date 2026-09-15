# Issue 236 / Issue 234 M1-A — one-interval multirate MultiApp smoke

This bounded stage constructs an actual MOOSE `TransientMultiApp` split before the
full M1 electron-timestep convergence sweep.

## Ownership

Parent:
- owns and executes the slow heavy/flow nonlinear solve (`solve = true`);
- owns the heavy solver variables and their time kernels;
- carries `n_e`, `n_epsilon`, and `potential_plasma` only as fast-state auxiliary mirrors;
- `dt_h = 1e-8 s`.

Fast child:
- nonlinear solver variables: `n_e`, `n_epsilon`, `potential_plasma`;
- transferred FV auxiliary mirrors: `p`, `w_O2s`, `w_O2p`, `w_O`, `w_Om`, `w_Op`, `w_Os`;
- flow velocities `u`, `v` are not solved or mirrored in the fast child;
- `TransientMultiApp` subcycling enabled;
- construction smoke uses coarse-control `dt_e = 1e-10 s` (100 subcycles).

The coarse-control electron timestep is **not** promoted by this stage. The parent
also receives endpoint mirrors of the three fast variables only as a transfer/sync
discriminator. Final multirate conservation still requires parent-interval
integrated/averaged electron reaction, wall-current, and energy source transfers.

## Acceptance for M1-A

- split input construction audits pass;
- parent owns the heavy/flow nonlinear variables while fast variables are auxiliary mirrors only;
- child owns only the three fast nonlinear variables;
- parent-to-child heavy-state copy transfer is exact by variable identity;
- child-to-parent fast endpoint mirror transfer is exact;
- child reaches the parent synchronization time through subcycling;
- real `physics-opt` runtime completes one parent interval.

A green M1-A authorizes the registered M1 convergence sweep:
`dt_e = 1e-10, 2e-11, 1e-11, 5e-12 s` at fixed `dt_h = 1e-8 s`.
