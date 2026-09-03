# Issue #27 A1 controlled wall-flux discriminator.
#
# This is deliberately NOT a reactor model. It tests only the finite-volume
# boundary-flux sign and N-1 constrained-O2 bookkeeping for
#
#   O -> 0.5 O2.
#
# Positive wall_mass_flux_O is intended to mean outward-from-plasma O mass
# flux. A1 runtime evidence must confirm that convention before any sticking
# law is promoted.

rho_value = 1.0
initial_w_O = 0.1
wall_mass_flux_O = 0.0016
dt_value = 0.1

[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 8
  xmin = 0
  xmax = 1
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [w_O]
    type = MooseVariableFVReal
    initial_condition = ${initial_w_O}
  []
[]

[FunctorMaterials]
  [rho_constant]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_mat'
    prop_values = '${rho_value}'
  []

  [O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O'
    functor_symbols = 'wo'
    expression = '1.0-wo'
  []

  [rho_w_O_material]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O
    functor_names = 'rho_mat w_O'
    functor_symbols = 'rho_s wo'
    expression = 'rho_s*wo'
  []

  [rho_w_O2_material]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O2
    functor_names = 'rho_mat w_O2_constraint'
    functor_symbols = 'rho_s wo2'
    expression = 'rho_s*wo2'
  []
[]

[FVKernels]
  [O_time]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w_O
    rho = rho_mat
  []
[]

[FVBCs]
  [O_wall_flux]
    type = FVNeumannBC
    variable = w_O
    boundary = right
    value = ${wall_mass_flux_O}
  []
[]

[Postprocessors]
  [wall_area]
    type = AreaPostprocessor
    boundary = right
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [O_mass]
    type = ADElementIntegralFunctorPostprocessor
    functor = w_O
    prefactor = rho_mat
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [O2_mass]
    type = ADElementIntegralFunctorPostprocessor
    functor = w_O2_constraint
    prefactor = rho_mat
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [total_oxygen_mass]
    type = ParsedPostprocessor
    pp_names = 'O_mass O2_mass'
    expression = 'O_mass+O2_mass'
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [w_O_min]
    type = ADElementExtremeFunctorValue
    functor = w_O
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [w_O2_min]
    type = ADElementExtremeFunctorValue
    functor = w_O2_constraint
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = ${dt_value}
  end_time = ${dt_value}
  nl_abs_tol = 1e-12
  nl_rel_tol = 1e-12
  nl_max_its = 20
[]

[Outputs]
  csv = true
  exodus = false
[]
