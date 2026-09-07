[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
  xmin = 0.0
  xmax = 1.0
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [n_epsilon]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
[]

[Functions]
  [phi_zero]
    type = ParsedFunction
    expression = '0*x'
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'p T_g carrier_one'
    prop_values = '101325.0 300.0 1.0'
  []
  [mean_energy_bridge]
    type = QPXElectronMeanEnergyMaterial
    electron_energy_density = n_epsilon
    electron_density = n_e
    energy_reference_eV = 5.73276
  []
  [electron_transport]
    type = QPXElectronTransportLookupMaterial
    property_table_file = electron_energy_lookup_response_smoke_table.txt
    mean_energy = mean_en_solved
    pressure = p
    gas_temperature = T_g
    bounds_policy = error
  []
[]

[FVKernels]
  [n_e_time]
    type = FVTimeKernel
    variable = n_e
  []
  [energy_time]
    type = FVTimeKernel
    variable = n_epsilon
  []
  [energy_diffusion]
    type = FVDiffusion
    variable = n_epsilon
    coeff = electron_energy_diffusion
  []
  [energy_drift]
    type = QPXFVElectrostaticDrift
    variable = n_epsilon
    potential = phi_zero
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
  []
[]

[Postprocessors]
  [mean_en_solved_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mean_en_solved
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
  dt = 1.0e-8
  end_time = 1.0e-8
  solve_type = NEWTON
[]

[Outputs]
  csv = true
[]
