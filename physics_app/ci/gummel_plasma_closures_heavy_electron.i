[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
  []
  [mean_en]
    type = MooseVariableFVReal
    initial_condition = 5.73276e16
  []
[]

[AuxVariables]
  [phi]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [T_g_from_heavy]
    type = MooseVariableFVReal
    initial_condition = 300.0
  []
  [p_gas_from_heavy]
    type = MooseVariableFVReal
    initial_condition = 100.0
  []
  [T_e_export]
    type = MooseVariableFVReal
    initial_condition = 30000.0
  []
[]

[PlasmaClosures]
  [electron]
    role = electron
    electron_state_form = physical_eV
    electron_number_density = n_e
    electron_energy_density = mean_en
    gas_pressure = p_gas_from_heavy
    gas_temperature = T_g_from_heavy
    electron_transport_table_file = plasma_closures_transport_table.txt
  []
[]

[AuxKernels]
  [export_electron_temperature]
    type = FunctorAux
    variable = T_e_export
    functor = electron_temperature_K
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
