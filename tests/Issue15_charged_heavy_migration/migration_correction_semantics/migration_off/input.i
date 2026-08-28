phi_left = 1
phi_right = 0
mu_value = 0.1

[Mesh]
  [base]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 4
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
  [phi]
    type = MooseVariableFVReal
    initial_condition = ${phi_left}
  []
  [w_ion]
    type = MooseVariableFVReal
  []
  [w_neutral]
    type = MooseVariableFVReal
  []
[]

[Functions]
  [ic_ion]
    type = ParsedFunction
    expression = '0.25 + 0.10*x'
  []
  [ic_neutral]
    type = ParsedFunction
    expression = '0.75 - 0.10*x'
  []
  [ic_phi]
    type = ParsedFunction
    expression = '${phi_left} + (${phi_right}-${phi_left})*x'
  []
[]

[ICs]
  [ion_ic]
    type = FunctionIC
    variable = w_ion
    function = ic_ion
  []
  [neutral_ic]
    type = FunctionIC
    variable = w_neutral
    function = ic_neutral
  []
  [phi_ic]
    type = FunctionIC
    variable = phi
    function = ic_phi
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho mobility'
    prop_values = '1.0 ${mu_value}'
  []
  [sum_w_material]
    type = ADParsedFunctorMaterial
    property_name = sum_w
    functor_names = 'w_ion w_neutral'
    functor_symbols = 'wi wn'
    expression = 'wi+wn'
  []
[]

[FVKernels]
  [phi_diffusion]
    type = FVDiffusion
    variable = phi
    coeff = 1.0
  []
  [ion_time]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w_ion
    rho = rho
  []
  [neutral_time]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w_neutral
    rho = rho
  []
[]

[FVBCs]
  [phi_left]
    type = FVDirichletBC
    variable = phi
    boundary = left
    value = ${phi_left}
  []
  [phi_right]
    type = FVDirichletBC
    variable = phi
    boundary = right
    value = ${phi_right}
  []
[]

[Postprocessors]
  [left_ion]
    type = ElementAverageFunctorPostprocessor
    functor = w_ion
    block = 0
  []
  [right_ion]
    type = ElementAverageFunctorPostprocessor
    functor = w_ion
    block = 1
  []
  [left_neutral]
    type = ElementAverageFunctorPostprocessor
    functor = w_neutral
    block = 0
  []
  [right_neutral]
    type = ElementAverageFunctorPostprocessor
    functor = w_neutral
    block = 1
  []

  [sum_w_min]
    type = ADElementExtremeFunctorValue
    functor = sum_w
    value_type = min
  []
  [sum_w_max]
    type = ADElementExtremeFunctorValue
    functor = sum_w
    value_type = max
  []
  [ion_min]
    type = ADElementExtremeFunctorValue
    functor = w_ion
    value_type = min
  []
  [ion_max]
    type = ADElementExtremeFunctorValue
    functor = w_ion
    value_type = max
  []
  [neutral_min]
    type = ADElementExtremeFunctorValue
    functor = w_neutral
    value_type = min
  []
  [neutral_max]
    type = ADElementExtremeFunctorValue
    functor = w_neutral
    value_type = max
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 0.01
  end_time = 0.01

  nl_abs_tol = 1e-12
  nl_rel_tol = 1e-10
  nl_max_its = 40

  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
