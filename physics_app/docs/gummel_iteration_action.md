# GummelIteration Action

`GummelIterationAction` supports two orchestration modes.

The preferred mode runs the electron and electrostatic systems as sibling MultiApps
inside a dedicated Gummel driver. When heavy particles are present, the heavy solve
lives one level above the driver so its state can remain frozen throughout inner
electron-Poisson convergence:

```text
OUTER_MAIN : heavy-particle FEProblem
  '- GUMMEL_DRIVER : solve = false, frozen heavy snapshot
       |- SUB_ELECTRON : solves n_e, mean_en; receives phi and frozen heavy state
       '- SUB_POISSON  : solves phi; receives n_e and frozen charged-heavy state
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

## Frozen-heavy outer coupling with PlasmaClosures

To keep the heavy state invariant during every inner Gummel iteration, place
the heavy FEProblem outside the Gummel Action and introduce a dedicated
`GUMMEL_DRIVER` MultiApp:

```text
OUTER_MAIN / HEAVY
  PlasmaClosures(role = heavy_transport)
  H^n = {T_g, p_gas, rho, w_k, ...}
       |
       | copy once before driver execution
       v
GUMMEL_DRIVER
  solve = false
  frozen snapshot H^n
       |
       +-- SUB_ELECTRON
       |     PlasmaClosures(role = electron)
       |     solves n_e, mean_en
       |
       '-- SUB_POISSON
             PlasmaClosures(role = electrostatic_charge)
             solves phi
```

The outer parent uses ordinary `MultiAppCopyTransfer` objects to snapshot
heavy state into the driver and to recover only the final fast state after the
driver returns:

```text
OUTER_MAIN.H^n
    -- TO_MULTIAPP before driver -->
GUMMEL_DRIVER.H_frozen

GUMMEL_DRIVER.{n_e,T_e,phi}_converged
    -- FROM_MULTIAPP after driver -->
OUTER_MAIN fast-state auxiliaries
```

A representative outer block is:

```text
[PlasmaClosures]
  [heavy]
    role = heavy_transport
    heavy_species_temperature = T_g
    heavy_species_pressure = p_gas
    electron_temperature = T_e_from_gummel
    electron_number_density = n_e_from_gummel
    heavy_transport_data_file = transport_data.txt
    heavy_species = 'O2 O2s O2p O Om Op Os'
    heavy_mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
  []
[]

[MultiApps]
  [gummel_driver]
    type = TransientMultiApp
    input_files = 'gummel_driver.i'
    execute_on = TIMESTEP_BEGIN
    no_restore = true
  []
[]

[Transfers]
  [heavy_snapshot_to_gummel]
    type = MultiAppCopyTransfer
    to_multi_app = gummel_driver
    source_variable = 'T_g p_gas rho w_O2p w_Om w_Op'
    variable =
      'T_g_frozen p_gas_frozen rho_frozen w_O2p_frozen w_Om_frozen w_Op_frozen'
  []

  [converged_gummel_to_heavy]
    type = MultiAppCopyTransfer
    from_multi_app = gummel_driver
    source_variable = 'n_e_converged T_e_converged phi_converged'
    variable = 'n_e_from_gummel T_e_from_gummel phi_from_gummel'
  []
[]
```

Inside `gummel_driver.i`, the `[GummelIteration]` Action owns only the
electron/Poisson inner coupling. Its four parent mapping pairs now refer to
the driver itself, not to the outer heavy solver:

- `parent_to_electron_source_variables` /
  `parent_to_electron_variables`
- `electron_to_parent_source_variables` /
  `electron_to_parent_variables`
- `parent_to_poisson_source_variables` /
  `parent_to_poisson_variables`
- `poisson_to_parent_source_variables` /
  `poisson_to_parent_variables`

For example:

```text
[GummelIteration]
  [electron_poisson]
    electron_input_file = electron_sub.i
    poisson_multiapp = poisson
    poisson_input_file = poisson_sub.i

    parent_to_electron_source_variables = 'T_g_frozen p_gas_frozen'
    parent_to_electron_variables = 'T_g_from_heavy p_gas_from_heavy'

    electron_to_parent_source_variables = 'n_e T_e_export'
    electron_to_parent_variables = 'n_e_converged T_e_converged'

    parent_to_poisson_source_variables =
      'rho_frozen w_O2p_frozen w_Om_frozen w_Op_frozen'
    parent_to_poisson_variables =
      'rho_from_heavy w_O2p_from_heavy w_Om_from_heavy w_Op_from_heavy'

    poisson_to_parent_source_variables = 'phi'
    poisson_to_parent_variables = 'phi_converged'
  []
[]
```

The driver snapshot variables are AuxVariables and are never advanced by a
heavy equation. Therefore, for every inner fixed-point iteration `k` in outer
heavy step `n`,

```text
H^(n,k) = H^n
```

by construction.

The resulting ordering is:

```text
outer step n:
  1. copy H^n -> GUMMEL_DRIVER frozen snapshot
  2. execute inner electron <-> Poisson fixed point until convergence
  3. copy converged n_e / T_e / phi -> OUTER_MAIN
  4. solve heavy equations once: H^n -> H^(n+1)
```

This preserves the slow/fast separation used by the qualified Gummel endpoint.
If an application instead places active heavy equations in the same FEProblem
that owns `[GummelIteration]`, it becomes a three-block fixed-point scheme and
does not satisfy the frozen-heavy contract.

Because `MultiAppCopyTransfer` writes into auxiliary variables, every receiving
target must be an AuxVariable. Derived FunctorMaterial outputs such as
`electron_temperature_K` should first be sampled into an export AuxVariable
(for example `T_e_export`) before a child-to-parent copy.

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

- OUTER_MAIN: heavy equations, slow-time integration, and heavy `PlasmaClosures`;
- GUMMEL_DRIVER: frozen heavy snapshot plus inner fixed-point policy;
- SUB_ELECTRON: electron equations and electron `PlasmaClosures`;
- SUB_POISSON: electrostatic equation, charge `PlasmaClosures`, and optional
  electron-response approximation.

The Action owns only the two inner MultiApps, driver/sibling field transfers,
ordering, and optional convergence object. The outer heavy coupling remains an
ordinary MOOSE MultiApp/Transfer layer.
