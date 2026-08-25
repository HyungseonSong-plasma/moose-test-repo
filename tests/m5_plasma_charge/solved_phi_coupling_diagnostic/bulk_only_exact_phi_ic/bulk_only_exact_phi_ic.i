rho0 = 1
mu_i = 0.01
z_i = 1
phi_left = 20000
phi_right = 0

[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 100
    xmin = 0
    xmax = 1
  []
[]

[Variables]
  [phi]
    type = MooseVariableFVReal
  []
  [w_O2_plus]
    type = MooseVariableFVReal
    scaling = 1e6
    two_term_boundary_expansion = false
  []
[]

[Functions]
  [x_coordinate]
    type = ParsedFunction
    expression = 'x'
  []
  [phi_exact]
    type = ParsedFunction
    expression = '20000*(1-x)'
  []
  [w_initial]
    type = ParsedFunction
    expression = '1e-6*(1+0.2*x)'
  []
[]

[ICs]
  [phi_exact_ic]
    type = FunctionIC
    variable = phi
    function = phi_exact
  []
  [w_ic]
    type = FunctionIC
    variable = w_O2_plus
    function = w_initial
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho ion_mobility relative_permittivity'
    prop_values = '${rho0} ${mu_i} 1.0'
  []
  [ion_mass_density]
    type = ADParsedFunctorMaterial
    property_name = ion_mass_density
    functor_names = 'rho w_O2_plus'
    functor_symbols = 'rho_f w_f'
    expression = 'rho_f*w_f'
  []
  [ion_mass_first_moment]
    type = ADParsedFunctorMaterial
    property_name = ion_mass_first_moment
    functor_names = 'ion_mass_density x_coordinate'
    functor_symbols = 'rho_i x_f'
    expression = 'rho_i*x_f'
  []
[]

[FVKernels]
  [potential_diffusion]
    type = FVDiffusion
    variable = phi
    coeff = relative_permittivity
  []
  [ion_time]
    type = QPXFVMassFractionTimeDerivative
    variable = w_O2_plus
    rho = rho
  []
  [ion_electrostatic_drift]
    type = QPXFVElectrostaticDrift
    variable = w_O2_plus
    potential = phi
    mobility = ion_mobility
    carrier = rho
    charge_number = ${z_i}
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
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
  [ion_mass_inventory]
    type = ElementIntegralFunctorPostprocessor
    functor = ion_mass_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ion_mass_first_moment]
    type = ElementIntegralFunctorPostprocessor
    functor = ion_mass_first_moment
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_min]
    type = ElementExtremeFunctorValue
    functor = phi
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_max]
    type = ElementExtremeFunctorValue
    functor = phi
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  solve_type = NEWTON
  automatic_scaling = true
  dt = 1e-5
  end_time = 2e-5
  nl_abs_tol = 3e-12
  nl_rel_tol = 1e-10
  nl_max_its = 30
  l_tol = 1e-12
  l_max_its = 200
[]

[Debug]
  show_var_residual_norms = true
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
