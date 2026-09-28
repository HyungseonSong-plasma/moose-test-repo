# P5/E7 bounded real-QVT chemistry-OFF integration oracle.
# Nonuniform particle and conserved-energy states diffuse on the accepted QVT
# plasma geometry. Natural FV boundaries provide zero normal diffusive flux.

[Mesh]
  coord_type = RZ
  rz_coord_axis = Y

  [main]
    type = FileMeshGenerator
    file = '../../experiments/Issue91_real_qvt_r3/r3_e0/qvt.msh'
  []
  [plasma_only]
    type = BlockDeletionGenerator
    input = main
    operation = keep
    block = plasma
  []
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    block = plasma
  []
  [mean_en]
    type = MooseVariableFVReal
    block = plasma
  []
[]

[Functions]
  [n_e_initial]
    type = ParsedFunction
    expression = '1.0e16*(0.9 + 0.2*x/0.2565)'
  []
  [mean_en_initial]
    type = ParsedFunction
    expression = '5.73276e16*(1.05 - 0.1*x/0.2565)'
  []
[]

[ICs]
  [n_e_ic]
    type = FunctionIC
    variable = n_e
    function = n_e_initial
    block = plasma
  []
  [mean_en_ic]
    type = FunctionIC
    variable = mean_en
    function = mean_en_initial
    block = plasma
  []
[]

[FunctorMaterials]
  [state_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'p T_g'
    prop_values = '101325.0 300.0'
    block = plasma
  []

  [mean_energy_bridge]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = mean_en
    electron_density = n_e
    state_form = physical_eV
    block = plasma
  []

  [electron_transport]
    type = PhysicsElectronTransportLookupMaterial
    property_table_file = '../../experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt'
    mean_energy = mean_en_solved
    pressure = p
    gas_temperature = T_g
    bounds_policy = error
    block = plasma
  []
[]

[FVKernels]
  [n_e_time]
    type = FVTimeKernel
    variable = n_e
    block = plasma
  []
  [n_e_diffusion]
    type = FVDiffusion
    variable = n_e
    coeff = electron_diffusion
    block = plasma
  []

  [mean_en_time]
    type = FVTimeKernel
    variable = mean_en
    block = plasma
  []
  [mean_en_diffusion]
    type = FVDiffusion
    variable = mean_en
    coeff = electron_energy_diffusion
    block = plasma
  []
[]

[Postprocessors]
  [n_e_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_en_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = mean_en
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [n_e_min]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_e_max]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_en_min]
    type = ADElementExtremeFunctorValue
    functor = mean_en
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_en_max]
    type = ADElementExtremeFunctorValue
    functor = mean_en
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_en_solved_min]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_en_solved_max]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [electron_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_diffusion
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_energy_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_energy_diffusion
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  dt = 1.0e-4
  end_time = 2.0e-4
  solve_type = NEWTON
  nl_rel_tol = 1.0e-10
  nl_abs_tol = 1.0e-12
[]

[Outputs]
  csv = true
[]
