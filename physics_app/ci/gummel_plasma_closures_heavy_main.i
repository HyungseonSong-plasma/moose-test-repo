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

  # Canonical Oxygen heavy-species mass fractions.  These sum to one.
  [w_O2]
    type = MooseVariableFVReal
    initial_condition = 0.99994
  []
  [w_O2s]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
  []
  [w_O2p]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
  []
  [w_O]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
  []
  [w_Om]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
  []
  [w_Op]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
  []
  [w_Os]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
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
[]

[PlasmaClosures]
  [heavy]
    role = heavy_transport

    heavy_species_temperature = T_g
    heavy_species_pressure = p_gas
    electron_temperature = T_e_from_gummel
    electron_number_density = n_e_from_gummel

    heavy_transport_data_file = plasma_closures_oxygen_transport.txt
    heavy_species = 'O2 O2s O2p O Om Op Os'
    heavy_mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
  []
[]

# OUTER coupling layer. The complete Oxygen heavy state is owned here.
# Only the heavy quantities consumed by the inner electron/Poisson solve are
# snapshotted once before Gummel begins; they remain frozen for all inner
# fixed-point iterations.
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
    source_variable = 'T_g p_gas rho w_O2p w_Om w_Op'
    variable = 'T_g_frozen p_gas_frozen rho_frozen w_O2p_frozen w_Om_frozen w_Op_frozen'
  []

  [converged_gummel_to_heavy]
    type = MultiAppCopyTransfer
    from_multi_app = gummel_driver
    source_variable = 'n_e_converged T_e_converged'
    variable = 'n_e_from_gummel T_e_from_gummel'
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
