rho0 = 1e-9
w_target_value = 1e-6
M_i = 0.032003320316217242
electron_density_value = 0

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
  [w_ion]
    type = MooseVariableFVReal
    initial_condition = 0
    scaling = 1e6
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho electron_density relative_permittivity w_target'
    prop_values = '${rho0} ${electron_density_value} 1 ${w_target_value}'
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
[]

[FVKernels]
  [w_reaction]
    type = FVReaction
    variable = w_ion
    rate = 1
  []
  [w_force]
    type = FVCoupledForce
    variable = w_ion
    v = w_target
  []
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
  [w_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_ion
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_avg]
    type = ElementAverageFunctorPostprocessor
    functor = phi
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_max]
    type = ElementExtremeFunctorValue
    functor = phi
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_min]
    type = ElementExtremeFunctorValue
    functor = phi
    value_type = min
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
  type = Steady
  solve_type = NEWTON
  nl_abs_tol = 1e-10
  nl_rel_tol = 1e-12
  nl_max_its = 20
  l_tol = 1e-12
  l_max_its = 200
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
