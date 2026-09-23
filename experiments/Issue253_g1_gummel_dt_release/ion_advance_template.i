# Issue #253 G1 follow-on: two-step O2+ ion advance discriminator.
# Scope: O2+ transient transport under prescribed E; electron density is frozen.
# A steady Poisson subapp observes the updated charge after INITIAL and each ion step.
# Poisson is intentionally one-way here: potential_observer does not drive the ion equation.

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
  [w_O2p]
    type = MooseVariableFVReal
    initial_condition = @@W_O2P@@
  []
[]

[AuxVariables]
  [log_e_for_poisson]
    type = MooseVariableFVReal
    initial_condition = @@LOG_CE@@
  []
  [w_Om_h]
    type = MooseVariableFVReal
    initial_condition = 0.001
  []
  [w_Op_h]
    type = MooseVariableFVReal
    initial_condition = 0.001
  []
  [potential_observer]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[Functions]
  [ion_ic]
    type = ParsedFunction
    expression = '@@W_O2P@@*(1.0 + 0.02*exp(-0.5*(x-0.003)*(x-0.003)/(0.001*0.001)))'
  []
  [phi_drift]
    type = ParsedFunction
    expression = '-@@E0@@*x'
  []
[]

[ICs]
  [ion_profile_ic]
    type = FunctionIC
    variable = w_O2p
    function = ion_ic
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const D_O2p mu_O2p Mn_const'
    prop_values = '1.3793506167141378e-5 @@D_O2P@@ @@MU_O2P@@ 0.032'
  []
  [rho_w_O2p]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O2p_functor
    functor_names = 'rho_const w_O2p'
    functor_symbols = 'rho wf'
    expression = 'rho*wf'
  []
  [ion_number_density]
    type = ADParsedFunctorMaterial
    property_name = n_O2p_m3
    functor_names = 'rho_const w_O2p'
    functor_symbols = 'rho wf'
    expression = 'rho*wf*6.02214076e23/0.032'
  []
[]

[FVKernels]
  [O2p_time]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w_O2p
    rho = rho_const
  []
  [O2p_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_O2p
    rho = rho_const
    diffusivity = D_O2p
    mean_molar_mass = Mn_const
    include_molar_mass_gradient = false
  []
  [O2p_drift]
    type = QPXFVElectrostaticDrift
    variable = w_O2p
    potential = phi_drift
    mobility = mu_O2p
    carrier = rho_const
    charge_number = 1
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
  []
[]

[MultiApps]
  [poisson_observer]
    type = FullSolveMultiApp
    input_files = poisson_sub.i
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Transfers]
  [log_e_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson_observer
    source_variable = log_e_for_poisson
    variable = log_e_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [O2p_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson_observer
    source_variable = w_O2p
    variable = w_O2p_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [Om_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson_observer
    source_variable = w_Om_h
    variable = w_Om_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [Op_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson_observer
    source_variable = w_Op_h
    variable = w_Op_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [phi_from_poisson]
    type = MultiAppCopyTransfer
    from_multi_app = poisson_observer
    source_variable = potential_plasma
    variable = potential_observer
    execute_on = SAME_AS_MULTIAPP
  []
[]

[Postprocessors]
  [ion_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O2p_functor
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ion_n_min]
    type = ADElementExtremeFunctorValue
    functor = n_O2p_m3
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ion_n_max]
    type = ADElementExtremeFunctorValue
    functor = n_O2p_m3
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_observer_min]
    type = ADElementExtremeFunctorValue
    functor = potential_observer
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_observer_max]
    type = ADElementExtremeFunctorValue
    functor = potential_observer
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[VectorPostprocessors]
  [ion_profile]
    type = ElementValueSampler
    variable = 'w_O2p potential_observer'
    sort_by = id
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = @@DT@@
  dtmin = @@DT@@
  dtmax = @@DT@@
  end_time = @@END_TIME@@
  num_steps = @@STEPS@@
  timestep_tolerance = 1.0e-12
  line_search = none
  nl_rel_tol = 1.0e-8
  nl_abs_tol = 1.0e-11
  nl_max_its = 80
  automatic_scaling = true
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
