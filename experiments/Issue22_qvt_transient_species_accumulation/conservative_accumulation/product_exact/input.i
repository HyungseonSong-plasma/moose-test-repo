[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 1
    xmin = 0.0
    xmax = 1.0
  []
[]

[Variables]
  [w]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
[]

[FunctorMaterials]
  [rho_time]
    type = ADParsedFunctorMaterial
    property_name = rho_test
    expression = '1.0 + t'
  []
[]

[FVKernels]
  [accumulation]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w
    rho = rho_test
  []
[]

[Postprocessors]
  [w_avg]
    type = ElementAverageValue
    variable = w
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 0.1
  end_time = 0.5

  nl_abs_tol = 1.0e-12
  nl_rel_tol = 1.0e-10
  nl_max_its = 20

  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
