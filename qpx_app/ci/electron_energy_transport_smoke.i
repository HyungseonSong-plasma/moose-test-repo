[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
  xmin = 0.0
  xmax = 1.0
[]

[Variables]
  [energy]
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
    prop_names = 'mean_en p T_g carrier_one'
    prop_values = '5.0 101325.0 300.0 1.0'
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
  [energy_time]
    type = FVTimeKernel
    variable = energy
  []
  [energy_diffusion]
    type = FVDiffusion
    variable = energy
    coeff = electron_energy_diffusion
  []
  [energy_drift]
    type = QPXFVElectrostaticDrift
    variable = energy
    potential = phi_zero
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
  []
[]

[Postprocessors]
  [electron_mobility_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_energy_mobility_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_energy_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_energy_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_energy_diffusion
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
