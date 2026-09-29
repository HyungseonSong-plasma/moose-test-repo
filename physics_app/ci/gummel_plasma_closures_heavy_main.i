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
  # Slow/heavy state owned by OUTER_MAIN.
  [T_g]
    type = MooseVariableFVReal
    # Heavy-gas temperature [K].
    initial_condition = 300.0
  []
  [p_gas]
    type = MooseVariableFVReal
    # Absolute gas pressure [Pa]; 10 mTorr = 1.333223684 Pa.
    initial_condition = 1.333223684
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

  # Final fast state imported only after the inner Gummel driver finishes.
  [n_e_from_gummel]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
  []
  [T_e_from_gummel]
    type = MooseVariableFVReal
    initial_condition = 30000.0
  []
  [phi_from_gummel]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[PlasmaClosures]
  [heavy]
    role = heavy_transport

    heavy_species_temperature = T_g
    heavy_species_pressure = p_gas
    electron_temperature = T_e_from_gummel
    electron_number_density = n_e_from_gummel

    heavy_transport_data_file = plasma_closures_heavy_transport.txt
    heavy_species = 'A B'
    heavy_mass_fractions = 'w_A w_B'
  []
[]

# OUTER coupling layer.  The heavy snapshot is copied into the driver once,
# then the driver completes its nested electron-Poisson Gummel solve before
# the final fast state is copied back to this parent.
[MultiApps]
  [gummel_driver]
    type = TransientMultiApp
    input_files = 'gummel_plasma_closures_driver.i'
    execute_on = TIMESTEP_BEGIN
    no_restore = true
  []
[]

[Transfers]
  [heavy_snapshot_to_gummel]
    type = MultiAppCopyTransfer
    to_multi_app = gummel_driver
    source_variable = 'T_g p_gas rho w_ion'
    variable = 'T_g_frozen p_gas_frozen rho_frozen w_ion_frozen'
  []

  [converged_gummel_to_heavy]
    type = MultiAppCopyTransfer
    from_multi_app = gummel_driver
    source_variable = 'n_e_converged T_e_converged phi_converged'
    variable = 'n_e_from_gummel T_e_from_gummel phi_from_gummel'
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
