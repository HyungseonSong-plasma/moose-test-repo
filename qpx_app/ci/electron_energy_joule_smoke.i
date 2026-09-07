[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
  xmin = 0.0
  xmax = 1.0
[]

[Variables]
  [energy_drift]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [energy_plus]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [energy_minus]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
[]

[Functions]
  [n_profile]
    type = ParsedFunction
    expression = '1.0 + 0.5*x'
  []
  [phi_plus]
    type = ParsedFunction
    expression = '-100.0*x'
  []
  [phi_minus]
    type = ParsedFunction
    expression = '100.0*x'
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en p T_g zero_diffusion'
    prop_values = '5.0 101325.0 300.0 0.0'
  []
  [electron_transport]
    type = QPXElectronTransportLookupMaterial
    property_table_file = electron_energy_transport_smoke_table.txt
    mean_energy = mean_en
    pressure = p
    gas_temperature = T_g
    bounds_policy = error
  []
[]

[FVKernels]
  [energy_drift_time]
    type = FVTimeKernel
    variable = energy_drift
  []
  [energy_drift_joule]
    type = QPXFVElectronEnergyJouleHeating
    variable = energy_drift
    electron_density = n_profile
    potential = phi_plus
    mobility = electron_mobility
    diffusion = zero_diffusion
    energy_reference_eV = 5.0
  []

  [energy_plus_time]
    type = FVTimeKernel
    variable = energy_plus
  []
  [energy_plus_joule]
    type = QPXFVElectronEnergyJouleHeating
    variable = energy_plus
    electron_density = n_profile
    potential = phi_plus
    mobility = electron_mobility
    diffusion = electron_diffusion
    energy_reference_eV = 5.0
  []

  [energy_minus_time]
    type = FVTimeKernel
    variable = energy_minus
  []
  [energy_minus_joule]
    type = QPXFVElectronEnergyJouleHeating
    variable = energy_minus
    electron_density = n_profile
    potential = phi_minus
    mobility = electron_mobility
    diffusion = electron_diffusion
    energy_reference_eV = 5.0
  []
[]

[Postprocessors]
  [energy_drift_avg]
    type = ElementAverageFunctorPostprocessor
    functor = energy_drift
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [energy_plus_avg]
    type = ElementAverageFunctorPostprocessor
    functor = energy_plus
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [energy_minus_avg]
    type = ElementAverageFunctorPostprocessor
    functor = energy_minus
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_mobility_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  dt = 1.0e-6
  end_time = 1.0e-6
  solve_type = NEWTON
[]

[Outputs]
  csv = true
[]
