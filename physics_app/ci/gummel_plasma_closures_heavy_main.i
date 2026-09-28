[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

[Problem]
  solve = false
  kernel_coverage_check = false
[]

[AuxVariables]
  [T_g]
    type = MooseVariableFVReal
    initial_condition = 300.0
  []
  [p_gas]
    type = MooseVariableFVReal
    initial_condition = 100.0
  []
  [rho]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [w_A]
    type = MooseVariableFVReal
    initial_condition = 0.5
  []
  [w_B]
    type = MooseVariableFVReal
    initial_condition = 0.5
  []
  [w_ion]
    type = MooseVariableFVReal
    initial_condition = 1.0e-6
  []

  # State imported from the two Gummel siblings.
  [n_e_from_electron]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
  []
  [T_e_from_electron]
    type = MooseVariableFVReal
    initial_condition = 30000.0
  []
  [phi_from_poisson]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[PlasmaClosures]
  [heavy]
    role = heavy_transport

    heavy_species_temperature = T_g
    heavy_species_pressure = p_gas
    electron_temperature = T_e_from_electron
    electron_number_density = n_e_from_electron

    heavy_transport_data_file = plasma_closures_heavy_transport.txt
    heavy_species = 'A B'
    heavy_mass_fractions = 'w_A w_B'
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

    # Heavy parent -> electron closure state.
    parent_to_electron_source_variables = 'T_g p_gas'
    parent_to_electron_variables = 'T_g_from_heavy p_gas_from_heavy'

    # Electron closure state -> heavy parent.
    electron_to_parent_source_variables = 'n_e T_e_export'
    electron_to_parent_variables = 'n_e_from_electron T_e_from_electron'

    # Heavy charged state -> Poisson charge closure.
    parent_to_poisson_source_variables = 'rho w_ion'
    parent_to_poisson_variables = 'rho_from_heavy w_ion_from_heavy'

    # Electrostatic state -> heavy parent.
    poisson_to_parent_source_variables = 'phi'
    poisson_to_parent_variables = 'phi_from_poisson'

    poisson_transformed_variables = 'phi'
    relaxation_factor = 0.45
    no_restore = true
    manage_convergence = false
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
