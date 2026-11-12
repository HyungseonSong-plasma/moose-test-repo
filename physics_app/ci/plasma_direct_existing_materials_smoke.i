# This is a checked-in input of already-implemented Material types, not a C++ generator.
# This replaces a redundant combined electron Closure with separate state and DD transport.
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
  [electron_number_density_physical]
    type = MooseVariableFVReal
    initial_condition = 1.0e15
  []
  [electron_energy_density_physical]
    type = MooseVariableFVReal
    initial_condition = 3.0e15
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

[FunctorMaterials]
  # Mean energy and temperature are state closures, not transport coefficients.
  [electron_mean_energy]
    type = PhysicsElectronMeanEnergyMaterial
    state_form = physical_eV
    electron_density = electron_number_density_physical
    electron_energy_density = electron_energy_density_physical
    mean_energy_output = electron_mean_energy_eV
  []
  [electron_temperature]
    type = ADParsedFunctorMaterial
    property_name = electron_temperature_K
    functor_names = 'electron_mean_energy_eV'
    functor_symbols = 'mean_eV'
    expression = '(2/3)*mean_eV*1.602176634e-19/1.380649e-23'
  []
  # One lookup owner of electron mobility, diffusivity and 5/3 energy transport.
  [electron]
    type = DDMaterial
    species_id = e
    model = lookup
    mean_energy = electron_mean_energy_eV
    pressure = gas_pressure
    gas_temperature = gas_temperature
    table_file = plasma_closures_transport_table.txt
  []
  [reaction_A]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = plasma_closures_rate_a.txt
    mean_energy = electron_mean_energy_eV
    electron_number_density = electron_number_density_physical
    target_molar_concentration = target_A_molar_concentration
    reaction_progress = electron_reaction_A
  []
  [reaction_B]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = plasma_closures_rate_b.txt
    mean_energy = electron_mean_energy_eV
    electron_number_density = electron_number_density_physical
    target_molar_concentration = target_B_molar_concentration
    reaction_progress = electron_reaction_B
  []
  [heavy]
    type = NVMaterial
    temperature = gas_temperature
    pressure = gas_pressure
    transport_data_file = plasma_closures_heavy_transport.txt
    species = 'A B'
    mass_fractions = 'mass_fraction_A mass_fraction_B'
  []
  [charge]
    type = PhysicsPlasmaChargeDensityMaterial
    density = mixture_density
    electron_density = electron_number_density_physical
    ion_ids = 'ion'
    ion_mass_fractions = charged_mass_fraction
    ion_molar_masses = '0.032'
    ion_charges = '1'
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
