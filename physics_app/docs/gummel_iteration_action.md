# GummelIteration Action

`GummelIterationAction` supports two orchestration modes.

The preferred mode runs the electron and electrostatic systems as sibling MultiApps.
The parent may be orchestration-only or may own local heavy-particle physics:

```text
MAIN : orchestration-only or heavy-particle FEProblem
 |- SUB_ELECTRON : solves n_e, mean_en; receives phi and mapped heavy state
 '- SUB_POISSON  : solves phi; receives n_e and mapped heavy charge state
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

## Heavy parent with PlasmaClosures

A parent application that owns heavy-particle state can combine
`[PlasmaClosures] role = heavy_transport` with the sibling Gummel topology.
The Gummel Action still does not construct heavy equations or closures; it only
maps parent variables to the two siblings and maps selected sibling state back
to parent auxiliary variables.

```text
MAIN / heavy
  PlasmaClosures(role = heavy_transport)
  T_g, p_gas, rho, heavy mass fractions
       |                         ^
       | parent -> electron      | electron -> parent
       v                         |
SUB_ELECTRON --------------------
  PlasmaClosures(role = electron)
  solves n_e, mean_en; exports T_e

MAIN / heavy
       |                         ^
       | parent -> Poisson       | Poisson -> parent
       v                         |
SUB_POISSON ---------------------
  PlasmaClosures(role = electrostatic_charge)
  solves phi
```

The four optional mapping pairs are:

- `parent_to_electron_source_variables` /
  `parent_to_electron_variables`
- `electron_to_parent_source_variables` /
  `electron_to_parent_variables`
- `parent_to_poisson_source_variables` /
  `parent_to_poisson_variables`
- `poisson_to_parent_source_variables` /
  `poisson_to_parent_variables`

A representative parent block is:

```text
[PlasmaClosures]
  [heavy]
    role = heavy_transport
    heavy_species_temperature = T_g
    heavy_species_pressure = p_gas
    electron_temperature = T_e_from_electron
    electron_number_density = n_e_from_electron
    heavy_transport_data_file = transport_data.txt
    heavy_species = 'O2 O2s O2p O Om Op Os'
    heavy_mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
  []
[]

[GummelIteration]
  [electron_poisson]
    electron_input_file = sub_electron.i
    poisson_multiapp = poisson
    poisson_input_file = sub_poisson.i

    parent_to_electron_source_variables = 'T_g p_gas'
    parent_to_electron_variables = 'T_g_from_heavy p_gas_from_heavy'

    electron_to_parent_source_variables = 'n_e T_e_export'
    electron_to_parent_variables = 'n_e_from_electron T_e_from_electron'

    parent_to_poisson_source_variables = 'rho w_O2p w_Om w_Op'
    parent_to_poisson_variables =
      'rho_from_heavy w_O2p_from_heavy w_Om_from_heavy w_Op_from_heavy'

    poisson_to_parent_source_variables = 'phi'
    poisson_to_parent_variables = 'phi_from_poisson'
  []
[]
```

Because `MultiAppCopyTransfer` writes into auxiliary variables, every receiving
target in these parent-state mappings must be an AuxVariable. Derived
FunctorMaterial outputs such as `electron_temperature_K` should first be
sampled into an export AuxVariable (for example `T_e_export`) before a
child-to-parent copy.

On the pinned MOOSE revision, parent-to-child transfers use
`SAME_AS_MULTIAPP` and occur before the associated child solve, while
child-to-parent transfers occur after that child solve. With an actively solved
heavy parent, the resulting fixed-point ordering is therefore a three-block
coupling rather than a frozen-heavy inner Gummel:

```text
TIMESTEP_BEGIN : heavy(previous) -> electron -> electron solve -> electron -> heavy
parent solve   : heavy update
TIMESTEP_END   : heavy(updated)  -> Poisson  -> Poisson solve  -> Poisson -> heavy
```

If strict time-scale separation requires the heavy state to remain frozen until
electron-Poisson convergence, keep the heavy solve outside this fixed-point
cycle and use this mapping surface only at the outer coupling boundary.

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

- MAIN: fixed-point policy and optionally local heavy-particle physics;
- SUB_ELECTRON: electron density/energy/momentum equations;
- SUB_POISSON: electrostatic equation and optional electron-response
  approximation.

The Action owns only the MultiApps, sibling/parent field transfers, ordering,
and optional convergence object. PlasmaClosures remains the local physics
composition layer in each FEProblem.
