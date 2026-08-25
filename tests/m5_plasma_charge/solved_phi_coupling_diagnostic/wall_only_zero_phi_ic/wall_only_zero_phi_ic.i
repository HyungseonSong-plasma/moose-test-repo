rho0 = 1
M_i = 0.032003320316217242
T_g = 300
N_A = 6.0220000000000003e+23
mu_i = 0.01
z_i = 1
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
    initial_condition = 0
  []
  [w_O2_plus]
    type = MooseVariableFVReal
    initial_condition = 1e-6
    scaling = 1e6
    two_term_boundary_expansion = false
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho ion_mobility gas_temperature relative_permittivity'
    prop_values = '${rho0} ${mu_i} ${T_g} 1.0'
  []
  [ion_number_density]
    type = ADParsedFunctorMaterial
    property_name = ion_number_density
    functor_names = 'rho w_O2_plus'
    functor_symbols = 'rho_f w_f'
    expression = 'rho_f*w_f*${N_A}/${M_i}'
  []
  [ion_mass_density]
    type = ADParsedFunctorMaterial
    property_name = ion_mass_density
    functor_names = 'rho w_O2_plus'
    functor_symbols = 'rho_f w_f'
    expression = 'rho_f*w_f'
  []
  [ion_wall_flux]
    type = QPXIonWallFluxMaterial
    ion_number_density = ion_number_density
    potential = phi
    mobility = ion_mobility
    gas_temperature = gas_temperature
    charge_number = ${z_i}
    molar_mass = ${M_i}
    sticking = 0
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
  [left_migration_loss]
    type = FVFunctorNeumannBC
    variable = w_O2_plus
    boundary = left
    functor = ion_migration_mass_flux
    factor = -1
    absolute_value_vector_tags = 'absolute_ref'
  []
  [right_migration_loss]
    type = FVFunctorNeumannBC
    variable = w_O2_plus
    boundary = right
    functor = ion_migration_mass_flux
    factor = -1
    absolute_value_vector_tags = 'absolute_ref'
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
    converge_on = 'w_O2_plus'
    normalization_type = global_L2
    unscale_the_residual = true
    zero_reference_residual_treatment = relative_tolerance
    nl_abs_tol = 3e-12
    nl_rel_tol = 1e-6
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
  [ion_mass_inventory]
    type = ElementIntegralFunctorPostprocessor
    functor = ion_mass_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [left_migration_mass_loss_rate]
    type = SideFVFluxBCIntegral
    boundary = left
    fvbcs = 'left_migration_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [right_migration_mass_loss_rate]
    type = SideFVFluxBCIntegral
    boundary = right
    fvbcs = 'right_migration_loss'
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
  nonlinear_convergence = combined
  dt = 1e-5
  end_time = 2e-5
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
