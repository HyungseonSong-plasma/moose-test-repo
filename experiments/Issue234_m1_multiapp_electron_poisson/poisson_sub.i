# Issue #234 nested Poisson subapp.
# Frozen electron + heavy-ion state is transferred before each solve.

[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 20
  xmin = 0.0
  xmax = 0.01
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [potential_plasma]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[AuxVariables]
  [log_e_frozen]
    type = MooseVariableFVReal
    initial_condition = -15.610953362044896
  []
  [w_O2p_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.00038523381586724926
  []
  [w_Om_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.001
  []
  [w_Op_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.001
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const relative_permittivity'
    prop_values = '1.3793506167141378e-5 1.0'
  []
  [electron_density]
    type = ADParsedFunctorMaterial
    property_name = electron_density_m3
    functor_names = 'log_e_frozen'
    functor_symbols = 'loge'
    expression = '6.02214076e23*exp(loge)'
  []
  [plasma_charge]
    type = PhysicsPlasmaChargeDensityMaterial
    density = rho_const
    electron_density = electron_density_m3
    ion_ids = 'O2p Om Op'
    ion_mass_fractions = 'w_O2p_frozen w_Om_frozen w_Op_frozen'
    ion_molar_masses = '0.032 0.016 0.016'
    ion_charges = '1 -1 1'
  []
[]

[FVKernels]
  [phi_diffusion]
    type = FVDiffusion
    variable = potential_plasma
    coeff = relative_permittivity
  []
  [phi_charge_source]
    type = FVCoupledForce
    variable = potential_plasma
    v = poisson_charge_source
    coef = 1.0
  []
[]

[FVBCs]
  [left_ground]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = left
    value = 0.0
  []
[]

[Postprocessors]
  [charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density
    execute_on = 'INITIAL FINAL'
  []
  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = min
    execute_on = 'INITIAL FINAL'
  []
  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = max
    execute_on = 'INITIAL FINAL'
  []
  [gauss_flux_reduced]
    type = SideDiffusiveFluxIntegral
    variable = potential_plasma
    boundary = 'left right'
    functor_diffusivity = relative_permittivity
    execute_on = 'INITIAL FINAL'
  []
  [gauss_flux_charge]
    type = ScalePostprocessor
    value = gauss_flux_reduced
    scaling_factor = 8.8541878128e-12
    execute_on = 'INITIAL FINAL'
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1.0e-10
  nl_abs_tol = 1.0e-12
  nl_max_its = 20
  automatic_scaling = true
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  csv = true
  exodus = true
  execute_on = 'INITIAL FINAL'
[]
