[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

[Problem]
  kernel_coverage_check = false
  solve = false
[]

[AuxVariables]
  [electron_density_normalized]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [electron_energy_density_normalized]
    type = MooseVariableFVReal
    initial_condition = 3.0
  []
  [electron_number_density_physical]
    type = MooseVariableFVReal
    initial_condition = 1.0e15
  []
  [gas_pressure]
    type = MooseVariableFVReal
    initial_condition = 100.0
  []
  [gas_temperature]
    type = MooseVariableFVReal
    initial_condition = 300.0
  []
  [mixture_density]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [mass_fraction_A]
    type = MooseVariableFVReal
    initial_condition = 0.5
  []
  [mass_fraction_B]
    type = MooseVariableFVReal
    initial_condition = 0.5
  []
  [charged_mass_fraction]
    type = MooseVariableFVReal
    initial_condition = 1.0e-6
  []
  [target_A_molar_concentration]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [target_B_molar_concentration]
    type = MooseVariableFVReal
    initial_condition = 2.0
  []
[]

[PlasmaClosures]
  [plasma]
    create_electron_closure = true
    normalized_electron_density = electron_density_normalized
    normalized_electron_energy_density = electron_energy_density_normalized
    electron_energy_reference_eV = 1.0
    gas_pressure = gas_pressure
    gas_temperature = gas_temperature
    electron_transport_table_file = plasma_closures_transport_table.txt

    create_electron_kinetics = true
    electron_number_density = electron_number_density_physical
    electron_impact_rate_table_files =
      'plasma_closures_rate_a.txt plasma_closures_rate_b.txt'
    electron_impact_target_molar_concentrations =
      'target_A_molar_concentration target_B_molar_concentration'
    electron_impact_reaction_progress_names =
      'electron_reaction_A electron_reaction_B'

    create_heavy_transport = true
    heavy_transport_data_file = plasma_closures_heavy_transport.txt
    heavy_species = 'A B'
    heavy_mass_fractions = 'mass_fraction_A mass_fraction_B'

    create_charge_density = true
    mixture_density = mixture_density
    charged_species_ids = 'ion'
    charged_species_mass_fractions = 'charged_mass_fraction'
    charged_species_molar_masses = '0.032'
    charged_species_charge_numbers = '1'
  []
[]

[Postprocessors]
  [mean_energy]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mean_energy_eV
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_temperature]
    type = ElementAverageFunctorPostprocessor
    functor = electron_temperature_K
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_mobility]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [reaction_A]
    type = ElementAverageFunctorPostprocessor
    functor = electron_reaction_A
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [reaction_B]
    type = ElementAverageFunctorPostprocessor
    functor = electron_reaction_B
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_A]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_A
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_density]
    type = ElementAverageFunctorPostprocessor
    functor = charge_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  dt = 1.0
  num_steps = 1
[]

[Outputs]
  csv = true
[]
