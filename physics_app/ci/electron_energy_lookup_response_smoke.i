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
    initial_condition = 1.0e16
  []
  [mean_en]
    type = MooseVariableFVReal
    initial_condition = 5.73276e16
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
  [fixture_log_molar_density]
    type = ADParsedFunctorMaterial
    property_name = fixture_log_molar_density
    functor_names = 'n_e'
    functor_symbols = 'ne'
    expression = 'log(ne/6.02214076e23)'
  []
  [fixture_log_molar_energy]
    type = ADParsedFunctorMaterial
    property_name = fixture_log_molar_energy
    functor_names = 'mean_en'
    functor_symbols = 'energy'
    expression = 'log(energy/6.02214076e23)'
  []
  [mean_energy_bridge]
    type = ElectronEnergyMaterial
    electron_energy_density = fixture_log_molar_energy
    electron_density = fixture_log_molar_density
    state_form = log_molar_eV
  []
  [electron_transport]
    type = DDTransportMaterial
    model = lookup
    table_file = electron_energy_lookup_response_smoke_table.txt
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
    variable = mean_en
  []
  [energy_diffusion]
    type = FVDiffusion
    variable = mean_en
    coeff = electron_energy_diffusion
  []
  [energy_drift]
    type = FVAdvection
    variable = mean_en
    velocity = '0 0 0'
    advected_interp_method = upwind
  []
[]

[Postprocessors]
  [e_energy_eV_avg]
    type = ElementAverageFunctorPostprocessor
    functor = e_energy_eV
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
