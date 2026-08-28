# R16 EVR1 controlled charge/Poisson discriminator
# case=electron_only
# Independent target scaled source S=-8.00000000000000000e+01 [V/m^2]
# Current-source constants audited separately: e=1.60199999999999998e-19, eps0=8.85000000000000046e-12, N_A=6.02200000000000027e+23

[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 200
    xmin = 0
    xmax = 1
  []
[]

[Variables]
  [phi]
    type = MooseVariableFVReal
    initial_condition = 0
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const w_ion_const ne_const relative_permittivity'
    prop_values = '1.0 0.00000000000000000e+00 4.41947565543071175e+09 1.0'
  []

  [charge]
    type = QPXPlasmaChargeDensityMaterial
    density = rho_const
    electron_density = ne_const
    ion_ids = 'ion'
    ion_mass_fractions = 'w_ion_const'
    ion_molar_masses = '0.032'
    ion_charges = '1.0'
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

[Postprocessors]
  [phi_avg]
    type = ElementAverageFunctorPostprocessor
    functor = phi
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
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1e-10
  nl_abs_tol = 1e-10
  nl_max_its = 30
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
