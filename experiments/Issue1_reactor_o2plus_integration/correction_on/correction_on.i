rho0 = 1.0
mu_i = 0.01
phi_left = 20000
phi_right = 0

[Problem]
  extra_tag_vectors = 'absolute_ref'
[]

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
  [w_ion]
    type = MooseVariableFVReal
    scaling = 10
    two_term_boundary_expansion = false
  []
  [w_neutral]
    type = MooseVariableFVReal
    scaling = 1
    two_term_boundary_expansion = false
  []
[]

[Functions]
  [phi_ic_fn]
    type = ParsedFunction
    expression = '20000*(1-x)'
  []
  [w_ion_ic_fn]
    type = ParsedFunction
    expression = '0.10 + 0.02*sin(2*pi*x)'
  []
  [w_neutral_ic_fn]
    type = ParsedFunction
    expression = '0.90 - 0.02*sin(2*pi*x)'
  []
[]

[ICs]
  [phi_ic]
    type = FunctionIC
    variable = phi
    function = phi_ic_fn
  []
  [w_ion_ic]
    type = FunctionIC
    variable = w_ion
    function = w_ion_ic_fn
  []
  [w_neutral_ic]
    type = FunctionIC
    variable = w_neutral
    function = w_neutral_ic_fn
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho mobility relative_permittivity'
    prop_values = '${rho0} ${mu_i} 1'
  []
  [sum_w]
    type = ADParsedFunctorMaterial
    property_name = heavy_mass_fraction_sum
    functor_names = 'w_ion w_neutral'
    functor_symbols = 'wi wn'
    expression = 'wi + wn'
  []
  [ion_mass_density]
    type = ADParsedFunctorMaterial
    property_name = ion_mass_density
    functor_names = 'rho w_ion'
    functor_symbols = 'rho_f wi'
    expression = 'rho_f*wi'
  []
  [neutral_mass_density]
    type = ADParsedFunctorMaterial
    property_name = neutral_mass_density
    functor_names = 'rho w_neutral'
    functor_symbols = 'rho_f wn'
    expression = 'rho_f*wn'
  []
[]

[FVKernels]
  [phi_diffusion]
    type = FVDiffusion
    variable = phi
    coeff = relative_permittivity
  []
  [ion_time]
    type = QPXFVMassFractionTimeDerivative
    variable = w_ion
    rho = rho
    absolute_value_vector_tags = 'absolute_ref'
  []
  [neutral_time]
    type = QPXFVMassFractionTimeDerivative
    variable = w_neutral
    rho = rho
    absolute_value_vector_tags = 'absolute_ref'
  []
  [ion_direct_drift]
    type = QPXFVElectrostaticDrift
    variable = w_ion
    potential = phi
    mobility = mobility
    carrier = rho
    charge_number = 1
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
    absolute_value_vector_tags = 'absolute_ref'
  []
  [ion_mass_correction]
    type = QPXFVHeavyMassElectromigrationCorrection
    variable = w_ion
    potential = phi
    rho = rho
    ion_mass_fractions = 'w_ion'
    ion_mobilities = 'mobility'
    ion_charges = '1'
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
    absolute_value_vector_tags = 'absolute_ref'
  []
  [neutral_mass_correction]
    type = QPXFVHeavyMassElectromigrationCorrection
    variable = w_neutral
    potential = phi
    rho = rho
    ion_mass_fractions = 'w_ion'
    ion_mobilities = 'mobility'
    ion_charges = '1'
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
    absolute_value_vector_tags = 'absolute_ref'
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

[Convergence]
  [global_default]
    type = DefaultNonlinearConvergence
    nl_abs_tol = 3e-12
    nl_rel_tol = 1e-10
    nl_max_its = 30
    nl_div_tol = -1
  []
  [species_reference]
    type = ReferenceResidualConvergence
    reference_vector = 'absolute_ref'
    converge_on = 'w_ion w_neutral'
    normalization_type = global_L2
    unscale_the_residual = true
    zero_reference_residual_treatment = relative_tolerance
    nl_abs_tol = 3e-12
    nl_rel_tol = 1e-8
    nl_max_its = 30
    nl_div_tol = -1
  []
  [combined]
    type = ParsedConvergence
    symbol_names = 'global_default species_reference'
    symbol_values = 'global_default species_reference'
    convergence_expression = 'global_default & species_reference'
    divergence_expression = 'global_default | species_reference'
  []
[]

[Postprocessors]
  [ion_mass]
    type = ElementIntegralFunctorPostprocessor
    functor = ion_mass_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_mass]
    type = ElementIntegralFunctorPostprocessor
    functor = neutral_mass_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sum_w_min]
    type = ElementExtremeFunctorValue
    functor = heavy_mass_fraction_sum
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sum_w_max]
    type = ElementExtremeFunctorValue
    functor = heavy_mass_fraction_sum
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ion_min]
    type = ElementExtremeFunctorValue
    functor = w_ion
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_min]
    type = ElementExtremeFunctorValue
    functor = w_neutral
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [nonlinear_iterations]
    type = NumNonlinearIterations
    execute_on = 'TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  solve_type = NEWTON
  automatic_scaling = true
  nonlinear_convergence = combined
  dt = 1e-5
  end_time = 1e-5
  l_tol = 1e-12
  l_max_its = 200
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
