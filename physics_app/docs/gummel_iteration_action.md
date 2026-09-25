# GummelIteration Action

`GummelIterationAction` owns the coupling between an electron subsystem in the
current application and a Poisson sub-application. It does **not** choose or
construct the electron equations.

The same Action therefore supports different electron models without a solver
branch inside the Gummel implementation.

## Drift-diffusion plus electron energy

```text
[GummelIteration]
  [electron_poisson]
    poisson_multiapp = poisson
    poisson_input_file = poisson_sub.i

    electron_state_variables = 'log_e n_epsilon'

    electron_to_poisson_source_variables = 'log_e n_epsilon'
    electron_to_poisson_variables = 'log_e_frozen n_epsilon_frozen'

    poisson_to_electron_source_variables = 'potential_plasma'
    poisson_to_electron_variables = 'potential_from_poisson'

    poisson_transformed_variables = 'potential_plasma'
    relaxation_factor = 0.45
    no_restore = true

    delta_phi_postprocessor = fp_delta_phi_max
    delta_phi_abs_tol = 1e-6
  []
[]
```

The electron density and energy equations remain ordinary `[FVKernels]`,
boundary conditions, materials, and sources in the surrounding input.

## Density, momentum, and electron energy

Only the electron subsystem changes:

```text
[GummelIteration]
  [electron_poisson]
    poisson_multiapp = poisson
    poisson_input_file = poisson_sub.i

    electron_state_variables = 'log_e electron_momentum n_epsilon'

    electron_to_poisson_source_variables = 'log_e n_epsilon'
    electron_to_poisson_variables = 'log_e_frozen n_epsilon_frozen'

    poisson_to_electron_source_variables = 'potential_plasma'
    poisson_to_electron_variables = 'potential_from_poisson'

    poisson_transformed_variables = 'potential_plasma'
    relaxation_factor = 0.45
    no_restore = true

    delta_phi_postprocessor = fp_delta_phi_max
    delta_phi_abs_tol = 1e-6
  []
[]
```

No Gummel code changes are required. Momentum is part of the electron state,
but it is transferred to Poisson only when a Poisson-side model explicitly
needs it.

## Responsibility boundary

The Action creates the Poisson MultiApp, the variable transfers, and the
optional delta-potential convergence object. The current application owns the
electron equations. The Poisson input owns the electrostatic equation and any
optional electron-response approximation such as
`FVElectronResponseBandedCorrection`.

This keeps these choices independent:

- electron equations: density only, density plus energy, or hydrodynamic
  density/momentum/energy;
- Gummel acceleration: configured with the parent Executioner's MOOSE
  fixed-point algorithm;
- Poisson response approximation: none, local, or banded.
