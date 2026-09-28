# GummelIteration Action

`GummelIterationAction` supports two orchestration modes.

The preferred mode keeps the parent application as an orchestrator and runs
the electron and electrostatic systems as sibling MultiApps:

```text
MAIN
 |- SUB_ELECTRON : solves n_e, mean_en; receives phi
 '- SUB_POISSON  : solves phi; receives n_e
```

The Action does not construct either subsystem's equations. Each input file
owns its local kernels, materials, boundary conditions, and solver settings.

## Preferred two-sub-application mode

```text
[GummelIteration]
  [electron_poisson]
    electron_multiapp = electron
    electron_input_file = sub_electron.i

    poisson_multiapp = poisson
    poisson_input_file = sub_poisson.i

    # Direct sibling sharing. These are also the defaults.
    electron_density_variable = n_e
    poisson_electron_density_variable = n_e

    poisson_potential_variable = phi
    electron_potential_variable = phi

    # Optional Poisson fixed-point transform / relaxation.
    poisson_transformed_variables = 'phi'
    relaxation_factor = 0.45
    no_restore = true

    # Optional extra sibling mappings, e.g. mean_en -> mean_en.
    electron_to_poisson_source_variables = 'mean_en'
    electron_to_poisson_variables = 'mean_en'

    manage_convergence = false
  []
[]
```

The two core sibling transfers are created automatically:

```text
SUB_ELECTRON.n_e  ---> SUB_POISSON.n_e   (AuxVariable)
SUB_POISSON.phi   ---> SUB_ELECTRON.phi  (AuxVariable)
```

Both sub-applications should use the same mesh when the default
`MultiAppCopyTransfer` is used.

The Action uses the pinned MOOSE execution schedule deliberately:

```text
fixed-point k, TIMESTEP_BEGIN:
  1. phi^(k-1) is copied SUB_POISSON -> SUB_ELECTRON
  2. SUB_ELECTRON solves n_e^(k), mean_en^(k)

fixed-point k, TIMESTEP_END:
  3. n_e^(k) is copied SUB_ELECTRON -> SUB_POISSON
  4. optional extra electron fields (for example mean_en) are copied
  5. SUB_POISSON solves phi^(k)

fixed-point k+1:
  6. phi^(k) is copied to SUB_ELECTRON before its next solve
```

This staggering is important for the MOOSE revision pinned by this repository.
That revision supports sibling `MultiAppCopyTransfer`, but sibling transfers
on a single execution flag run before the sibling MultiApps. Splitting the two
sub-solves across `TIMESTEP_BEGIN` and `TIMESTEP_END` therefore preserves
the intended Gauss-Seidel/Gummel ordering without requiring a framework
upgrade.

Additional fields may be shared with the two generic mapping pairs:

- `electron_to_poisson_source_variables` /
  `electron_to_poisson_variables`
- `poisson_to_electron_source_variables` /
  `poisson_to_electron_variables`

For example, `mean_en` may also be copied to Poisson when a Poisson-side
response model needs electron energy.

## Required sub-application interface

A minimal electron input owns the solved electron fields and an auxiliary
potential target:

```text
[Variables]
  [n_e]
    type = MooseVariableFVReal
    # physical density [1/m^3]
  []
  [mean_en]
    type = MooseVariableFVReal
    # electron energy density [eV/m^3]
  []
[]

[AuxVariables]
  [phi]
    type = MooseVariableFVReal
  []
[]
```

A minimal Poisson input owns the solved potential and an auxiliary electron
density target:

```text
[Variables]
  [phi]
    type = MooseVariableFVReal
  []
[]

[AuxVariables]
  [n_e]
    type = MooseVariableFVReal
  []
[]
```

The target fields must be auxiliary variables because `MultiAppCopyTransfer`
writes into the receiving application.

## Convergence

The existing `DeltaPhiMultiAppConvergence` remains optional. When it is
enabled, its delta-phi postprocessor is still owned by the parent application:

```text
[GummelIteration]
  [electron_poisson]
    # ... two-subapp parameters ...

    manage_convergence = true
    delta_phi_postprocessor = fp_delta_phi_max
    delta_phi_abs_tol = 1e-6
  []
[]

[Executioner]
  multiapp_fixed_point_convergence = gummel_delta_phi
[]
```

If the parent does not own such a postprocessor yet, use
`manage_convergence = false` and the standard MOOSE fixed-point convergence
until the parent-level metric is supplied.

## Legacy mode

For backwards compatibility, omitting `electron_input_file` retains the
previous architecture where the current application owns the electron
equations and only Poisson is a MultiApp. In that mode the explicit
electron-to-Poisson and Poisson-to-electron mapping lists are required.

## Responsibility boundary

The preferred architecture separates ownership cleanly:

- MAIN: MultiApp orchestration and fixed-point policy;
- SUB_ELECTRON: electron density/energy/momentum equations;
- SUB_POISSON: electrostatic equation and optional electron-response
  approximation.

The Action owns only the MultiApps, direct sibling field transfers, ordering,
and optional convergence object.
