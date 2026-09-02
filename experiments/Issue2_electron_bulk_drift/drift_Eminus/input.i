# R2 EVR1 T3: prescribed-field electron drift sign
[Mesh]
  [base]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 2
    xmin = 0
    xmax = 1
  []
  [split]
    type = ParsedSubdomainMeshGenerator
    input = base
    block_id = 1
    combinatorial_geometry = 'x > 0.5'
  []
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1e+16
  []
[]

[Functions]
  [phi_prescribed]
    type = ParsedFunction
    expression = '1.0*x'
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en p_abs T_g carrier_one'
    prop_values = '5.73276 101325.0 600.0 1.0'
  []
  [electron_transport]
    type = QPXElectronTransportLookupMaterial
    property_table_file = electron_moments.txt
    mean_energy = mean_en
    pressure = p_abs
    gas_temperature = T_g
    bounds_policy = error
  []
[]

[FVKernels]
  [time]
    type = FVTimeKernel
    variable = n_e
  []
  [drift]
    type = QPXFVElectrostaticDrift
    variable = n_e
    potential = phi_prescribed
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
  []
[]

[Postprocessors]
  [n_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
  []
  [n_min]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = min
  []
  [n_max]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = max
  []
  [inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e
  []
  [neutral_number_density_avg]
    type = ElementAverageFunctorPostprocessor
    functor = neutral_number_density
  []
  [electron_mobility_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mobility
  []
  [electron_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_diffusion
  []

  [left_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
    block = 0
  []
  [right_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
    block = 1
  []

  [domain_volume]
    type = ADElementIntegralFunctorPostprocessor
    functor = carrier_one
  []
[]


[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 0.1
  end_time = 0.1
  nl_rel_tol = 1e-8
  nl_max_its = 30
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = true
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]

