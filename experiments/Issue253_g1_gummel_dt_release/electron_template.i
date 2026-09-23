# Issue #253 G1: electron-particle / Poisson timestep-release discriminator.
# Electron energy, chemistry, RF heating, SEE, and heavy evolution are intentionally OFF.
# @@CASE_NAME@@ controls only dt and MultiApp fixed-point coupling.

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
  [log_e]
    type = MooseVariableFVReal
    initial_condition = @@LOG_CE@@
  []
[]

[AuxVariables]
  [w_O2p_h]
    type = MooseVariableFVReal
    initial_condition = @@W_O2P@@
  []
  [w_Om_h]
    type = MooseVariableFVReal
    initial_condition = 0.001
  []
  [w_Op_h]
    type = MooseVariableFVReal
    initial_condition = 0.001
  []
  [potential_from_poisson]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [electron_density_out]
    type = MooseVariableFVReal
    initial_condition = @@NE0@@
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en_eV electron_mobility electron_diffusion carrier_one'
    prop_values = '5.73276 9755.114369721427 41257.29899041419 1.0'
  []
  [electron_molar_density]
    type = ADParsedFunctorMaterial
    property_name = c_e_molar
    functor_names = 'log_e'
    functor_symbols = 'loge'
    expression = 'exp(loge)'
  []
  [electron_number_density]
    type = ADParsedFunctorMaterial
    property_name = electron_density_m3
    functor_names = 'log_e'
    functor_symbols = 'loge'
    expression = '6.02214076e23*exp(loge)'
  []
  [thermal_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = thermal_flux_molar_outward
    functor_names = 'log_e mean_en_eV'
    functor_symbols = 'loge mean_ev'
    expression = '0.25*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))'
  []
[]

[FVKernels]
  [electron_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_e
  []
  [electron_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_e
    coeff = electron_diffusion
    coeff_interp_method = harmonic
  []
  [electron_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_e
    potential = potential_from_poisson
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
  []
[]

[FVBCs]
  [right_thermal_surface_loss]
    type = FVFunctorNeumannBC
    variable = log_e
    boundary = right
    functor = thermal_flux_molar_outward
    factor = -1
  []
[]

[AuxKernels]
  [electron_density_copy]
    type = FunctorAux
    variable = electron_density_out
    functor = electron_density_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[MultiApps]
  [poisson]
    type = FullSolveMultiApp
    input_files = poisson_sub.i
    execute_on = TIMESTEP_END
  []
[]

[Transfers]
  [log_e_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = log_e
    variable = log_e_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [O2p_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = w_O2p_h
    variable = w_O2p_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [Om_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = w_Om_h
    variable = w_Om_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [Op_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = w_Op_h
    variable = w_Op_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [phi_from_poisson]
    type = MultiAppCopyTransfer
    from_multi_app = poisson
    source_variable = potential_plasma
    variable = potential_from_poisson
    execute_on = SAME_AS_MULTIAPP
  []
[]

[Postprocessors]
  [electron_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = c_e_molar
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_e_min]
    type = ADElementExtremeFunctorValue
    functor = electron_density_m3
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_e_max]
    type = ADElementExtremeFunctorValue
    functor = electron_density_m3
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_from_poisson
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_from_poisson
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
[]

[VectorPostprocessors]
  [electron_profile]
    type = ElementValueSampler
    variable = 'log_e electron_density_out potential_from_poisson'
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
  timestep_tolerance = @@TIMESTEP_TOL@@
  nl_rel_tol = 1.0e-9
  nl_abs_tol = 1.0e-13
  nl_max_its = 50
  automatic_scaling = false
  # FullSolveMultiApp rejects the transient fixed-point default auto_advance=false.
  # The Poisson subapp is steady, so re-solve it on every fixed-point iterate while
  # the parent electron solve remains on the same physical timestep.
  auto_advance = true
  fixed_point_min_its = @@FP_MIN@@
  fixed_point_max_its = @@FP_MAX@@
  fixed_point_rel_tol = 1.0e-8
  fixed_point_abs_tol = 1.0e-12
  accept_on_max_fixed_point_iteration = false
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  csv = true
  exodus = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
