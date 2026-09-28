[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

# Dedicated inner orchestration problem.  It never advances heavy physics.
[Problem]
  solve = false
  kernel_coverage_check = false
[]

[AuxVariables]
  # Heavy snapshot copied once from OUTER_MAIN before this driver executes.
  [T_g_frozen]
    type = MooseVariableFVReal
    initial_condition = 300.0
  []
  [p_gas_frozen]
    type = MooseVariableFVReal
    initial_condition = 100.0
  []
  [rho_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [w_ion_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0e-6
  []

  # Fast state accumulated during the inner solve and exported only after
  # the driver MultiApp returns to OUTER_MAIN.
  [n_e_converged]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
  []
  [T_e_converged]
    type = MooseVariableFVReal
    initial_condition = 30000.0
  []
  [phi_converged]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[GummelIteration]
  [electron_poisson]
    electron_multiapp = electron
    electron_input_file = gummel_plasma_closures_heavy_electron.i

    poisson_multiapp = poisson
    poisson_input_file = gummel_plasma_closures_heavy_poisson.i

    # Core sibling Gummel state.
    electron_density_variable = n_e
    poisson_electron_density_variable = n_e
    poisson_potential_variable = phi
    electron_potential_variable = phi

    electron_to_poisson_source_variables = 'mean_en'
    electron_to_poisson_variables = 'mean_en'

    # Frozen heavy snapshot -> electron closure.
    parent_to_electron_source_variables = 'T_g_frozen p_gas_frozen'
    parent_to_electron_variables = 'T_g_from_heavy p_gas_from_heavy'

    # Electron state -> driver export state.
    electron_to_parent_source_variables = 'n_e T_e_export'
    electron_to_parent_variables = 'n_e_converged T_e_converged'

    # Frozen charged-heavy snapshot -> Poisson charge closure.
    parent_to_poisson_source_variables = 'rho_frozen w_ion_frozen'
    parent_to_poisson_variables = 'rho_from_heavy w_ion_from_heavy'

    # Electrostatic state -> driver export state.
    poisson_to_parent_source_variables = 'phi'
    poisson_to_parent_variables = 'phi_converged'

    poisson_transformed_variables = 'phi'
    relaxation_factor = 0.45
    no_restore = true

    # Structural CI fixture. Production cases may enable DeltaPhi convergence
    # once the driver-level delta-phi postprocessor is supplied.
    manage_convergence = false
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
