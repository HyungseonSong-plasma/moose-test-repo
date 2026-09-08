rho0 = 1e-9
M_i = 0.032003320316217242
mu_i = 0.01
electron_density_value = 0

[Problem]
  extra_tag_vectors = 'absolute_ref'
[]

[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 50
    ny = 4
    xmin = 0
    xmax = 0.5
    ymin = 0
    ymax = 0.02
  []
[]

[Variables]
  [phi]
    type = MooseVariableFVReal
    initial_condition = 0
  []
  [w_ion]
    type = MooseVariableFVReal
    scaling = 1e6
    two_term_boundary_expansion = false
  []
  [w_neutral]
    type = MooseVariableFVReal
    scaling = 1
    two_term_boundary_expansion = false
  []
[]

[Functions]
  [w_ion_ic_fn]
    type = ParsedFunction
    expression = '1e-6*(1 + 4*exp(-300*(x-0.15)^2))'
  []
  [w_neutral_ic_fn]
    type = ParsedFunction
    expression = '1 - 1e-6*(1 + 4*exp(-300*(x-0.15)^2))'
  []
  [x_coordinate]
    type = ParsedFunction
    expression = 'x'
  []
[]

[ICs]
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
    prop_names = 'rho electron_density mobility relative_permittivity'
    prop_values = '${rho0} ${electron_density_value} ${mu_i} 1'
  []
  [charge_density]
    type = QPXPlasmaChargeDensityMaterial
    density = rho
    electron_density = electron_density
    ion_ids = 'O2p'
    ion_mass_fractions = 'w_ion'
    ion_molar_masses = '${M_i}'
    ion_charges = '1'
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
  [ion_first_moment_x]
    type = ADParsedFunctorMaterial
    property_name = ion_first_moment_x
    functor_names = 'ion_mass_density x_coordinate'
    functor_symbols = 'mi xpos'
    expression = 'mi*xpos'
  []
[]

[FVKernels]
  [phi_diffusion]
    type = FVDiffusion
    variable = phi
    coeff = relative_permittivity
  []
  [phi_charge_source]
    type = FVCoupledForce
    variable = phi
    v = poisson_charge_source
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
    boundaries_to_avoid = 'left right top bottom'
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
    boundaries_to_avoid = 'left right top bottom'
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
    boundaries_to_avoid = 'left right top bottom'
    absolute_value_vector_tags = 'absolute_ref'
  []
[]

[FVBCs]
  [phi_left]
    type = FVDirichletBC
    variable = phi
    boundary = left
    value = 0
  []
  [phi_right]
    type = FVDirichletBC
    variable = phi
    boundary = right
    value = 0
  []
[]

[Convergence]
  [global_default]
    type = DefaultNonlinearConvergence
    nl_abs_tol = 1e-12
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
    nl_abs_tol = 1e-12
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
  [ion_first_moment_x]
    type = ElementIntegralFunctorPostprocessor
    functor = ion_first_moment_x
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
  [nonlinear_iterations]
    type = NumNonlinearIterations
    execute_on = 'TIMESTEP_END'
  []
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Executioner]
  type = Transient
  solve_type = NEWTON
  automatic_scaling = true
  nonlinear_convergence = combined
  dt = 1e-3
  end_time = 1e-3
  l_tol = 1e-12
  l_max_its = 300
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
