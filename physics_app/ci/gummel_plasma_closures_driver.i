[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

# Dedicated inner orchestration problem. It never advances heavy physics.
[Problem]
  solve = false
  kernel_coverage_check = false
[]

[AuxVariables]
  # Heavy snapshot copied once from OUTER_MAIN before this driver executes.
  [T_g_frozen]
    type = MooseVariableFVReal
    # Frozen heavy-gas temperature [K].
    initial_condition = 300.0
  []
  [p_gas_frozen]
    type = MooseVariableFVReal
    # Frozen absolute gas pressure [Pa]; 10 mTorr = 1.333223684 Pa.
    initial_condition = 1.333223684
  []
  [rho_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []

  # Frozen charged Oxygen heavy species used by Poisson.
  [w_O2p_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
  []
  [w_Om_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
  []
  [w_Op_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
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
    electron_input_file = gummel_plasma_closures_heavy_electron.i

    poisson_multiapp = poisson
    poisson_input_file = gummel_plasma_closures_heavy_poisson.i

    # Core sibling Gummel n_e/phi names use the Action defaults.

    # Route potential through the driver so driver-level Steffensen transforms
    # the iterate before the next electron solve.
    potential_transfer_mode = through_parent
    parent_potential_variable = phi_converged

    # Frozen heavy thermodynamic snapshot -> electron closure.
    parent_to_electron_source_variables = 'T_g_frozen p_gas_frozen'
    parent_to_electron_variables = 'T_g_from_heavy p_gas_from_heavy'

    # Electron state -> driver export state.
    electron_to_parent_source_variables = 'n_e T_e_export'
    electron_to_parent_variables = 'n_e_converged T_e_converged'

    # Frozen charged-heavy Oxygen snapshot -> Poisson charge closure.
    parent_to_poisson_source_variables = 'rho_frozen w_O2p_frozen w_Om_frozen w_Op_frozen'
    parent_to_poisson_variables = 'rho_from_heavy w_O2p_from_heavy w_Om_from_heavy w_Op_from_heavy'

    # phi is returned automatically through parent_potential_variable.
    poisson_transformed_variables = 'phi'
    relaxation_factor = 0.45

    # Structural CI fixture. Production cases may enable DeltaPhi convergence
    # once the driver-level delta-phi postprocessor is supplied.
    manage_convergence = false
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1

  # The pinned MOOSE default is one fixed-point iteration. Explicitly enable
  # the inner loop; production qualification supplies the delta-phi convergence
  # object and tolerance on this driver.
  fixed_point_algorithm = steffensen
  transformed_variables = 'phi_converged'
  fixed_point_max_its = 3000
[]
