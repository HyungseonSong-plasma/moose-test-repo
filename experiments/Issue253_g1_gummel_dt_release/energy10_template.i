# Issue #253 G2: solved electron-energy + Joule-heating timestep sweep.
# COMSOL-consistent electron particle/energy wall fluxes are always ON.
# Joule heating is ON, O2 elastic energy exchange is OFF, heavy evolution is frozen.
# Sequence 10 varies only chi/dt and the matching Poisson Gummel relaxation.

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
  [n_epsilon]
    type = MooseVariableFVReal
    initial_condition = 1.0
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
  [mean_energy_out]
    type = MooseVariableFVReal
    initial_condition = 5.73276
  []
  [mobility_out]
    type = MooseVariableFVReal
    initial_condition = 9755.114369721427
  []
  [diffusion_out]
    type = MooseVariableFVReal
    initial_condition = 41257.29899041419
  []
  [elastic_loss_candidate_out]
    type = MooseVariableFVReal
    initial_condition = 4.622905967454569
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'p_gas T_g carrier_one zero_flux c_O2'
    prop_values = '0.66661 300.0 1.0 0.0 0.0002672491819834387'
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

  [electron_density_normalized]
    type = ADParsedFunctorMaterial
    property_name = electron_density_hat
    functor_names = 'electron_density_m3'
    functor_symbols = 'ne'
    expression = 'ne/1.0e16'
  []

  [mean_energy_bridge]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = n_epsilon
    electron_density = electron_density_hat
    energy_reference_eV = 5.73276
  []

  [electron_transport]
    type = PhysicsElectronTransportLookupMaterial
    property_table_file = electron_moments.txt
    mean_energy = mean_en_solved
    pressure = p_gas
    gas_temperature = T_g
    bounds_policy = error
  []

  [joule_transport_switch]
    type = ADParsedFunctorMaterial
    property_name = joule_mobility
    functor_names = 'electron_mobility'
    functor_symbols = 'mu'
    expression = '@@JOULE_FACTOR@@*mu'
  []

  [joule_diffusion_switch]
    type = ADParsedFunctorMaterial
    property_name = joule_diffusion
    functor_names = 'electron_diffusion'
    functor_symbols = 'diff'
    expression = '@@JOULE_FACTOR@@*diff'
  []

  [thermal_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = thermal_flux_molar_outward
    functor_names = 'log_e mean_en_solved'
    functor_symbols = 'loge mean_ev'
    expression = '0.5*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))'
  []

  [electron_energy_density_physical]
    type = ADParsedFunctorMaterial
    property_name = electron_energy_J_m3
    functor_names = 'n_epsilon'
    functor_symbols = 'eps_hat'
    expression = '1.0e16*5.73276*1.602176634e-19*eps_hat'
  []

  [elastic_o2_rate]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = o2_elastic.txt
    mean_energy = mean_en_solved
    electron_number_density = electron_density_m3
    target_molar_concentration = c_O2
    reaction_progress = R_elastic_O2
  []

  [elastic_energy_candidate]
    type = ADParsedFunctorMaterial
    property_name = S_elastic_candidate_hat
    functor_names = 'mean_en_solved T_g R_elastic_O2'
    functor_symbols = 'meanE tgas rprog'
    expression = '-540.2881732575735*(0.66666666666666663*meanE-8.617333262145e-5*tgas)*rprog'
  []

  [elastic_energy_applied]
    type = ADParsedFunctorMaterial
    property_name = S_elastic_applied_hat
    functor_names = 'S_elastic_candidate_hat'
    functor_symbols = 'source'
    expression = '@@ELASTIC_FACTOR@@*source'
  []

  [elastic_loss_candidate_physical]
    type = ADParsedFunctorMaterial
    property_name = elastic_loss_candidate_W_m3
    functor_names = 'S_elastic_candidate_hat'
    functor_symbols = 'source'
    expression = '-source*1.0e16*5.73276*1.602176634e-19'
  []

  [elastic_loss_applied_physical]
    type = ADParsedFunctorMaterial
    property_name = elastic_loss_applied_W_m3
    functor_names = 'S_elastic_applied_hat'
    functor_symbols = 'source'
    expression = '-source*1.0e16*5.73276*1.602176634e-19'
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

  [energy_time]
    type = FVTimeKernel
    variable = n_epsilon
  []
  [energy_diffusion]
    type = FVDiffusion
    variable = n_epsilon
    coeff = electron_energy_diffusion
  []
  [energy_drift]
    type = PhysicsFVElectrostaticDrift
    variable = n_epsilon
    potential = potential_from_poisson
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
  []
  [energy_joule]
    type = PhysicsFVElectronEnergyJouleHeating
    variable = n_epsilon
    electron_density = electron_density_hat
    potential = potential_from_poisson
    mobility = joule_mobility
    diffusion = joule_diffusion
    energy_reference_eV = 5.73276
  []
  [energy_elastic_o2]
    type = FVCoupledForce
    variable = n_epsilon
    v = S_elastic_applied_hat
    coef = 1.0
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

  [right_energy_surface_loss]
    type = PhysicsFVElectronEnergyWallFluxBC
    variable = n_epsilon
    boundary = right
    electron_energy_density = n_epsilon
    mean_electron_energy = mean_en_solved
    see_number_flux = zero_flux
    energy_reference_eV = 5.73276
  []
[]

[AuxKernels]
  [electron_density_copy]
    type = FunctorAux
    variable = electron_density_out
    functor = electron_density_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_copy]
    type = FunctorAux
    variable = mean_energy_out
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mobility_copy]
    type = FunctorAux
    variable = mobility_out
    functor = electron_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [diffusion_copy]
    type = FunctorAux
    variable = diffusion_out
    functor = electron_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_loss_candidate_copy]
    type = FunctorAux
    variable = elastic_loss_candidate_out
    functor = elastic_loss_candidate_W_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[MultiApps]
  [poisson]
    type = FullSolveMultiApp
    input_files = poisson_sub.i
    execute_on = TIMESTEP_END
    relaxation_factor = @@RELAXATION_FACTOR@@
    transformed_variables = 'potential_plasma'
    keep_solution_during_restore = true
    update_old_solution_when_keeping_solution_during_restore = false
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
  [energy_inventory_J_m2]
    type = ADElementIntegralFunctorPostprocessor
    functor = electron_energy_J_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_avg_eV]
    type = ElementAverageFunctorPostprocessor
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_min_eV]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_max_eV]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_mobility_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_loss_candidate_W_m2]
    type = ADElementIntegralFunctorPostprocessor
    functor = elastic_loss_candidate_W_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_loss_applied_W_m2]
    type = ADElementIntegralFunctorPostprocessor
    functor = elastic_loss_applied_W_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wall_particle_rate_mol_m2_s]
    type = SideFVFluxBCIntegral
    boundary = right
    fvbcs = 'right_thermal_surface_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wall_energy_rate_hat]
    type = SideFVFluxBCIntegral
    boundary = right
    fvbcs = 'right_energy_surface_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wall_energy_power_W_m2]
    type = ScalePostprocessor
    value = wall_energy_rate_hat
    scaling_factor = 0.009184903764514185
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
  [cumulative_fixed_point_iterations]
    type = CumulativeValuePostprocessor
    postprocessor = fixed_point_iterations
    execute_on = 'TIMESTEP_END'
  []
[]

[VectorPostprocessors]
  [energy_profile]
    type = ElementValueSampler
    variable = 'electron_density_out potential_from_poisson n_epsilon mean_energy_out mobility_out diffusion_out elastic_loss_candidate_out'
    sort_by = id
    execute_on = 'FINAL'
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
  # Sequence-10 chi=1 reached a parent nonlinear residual floor of 2.024e-7.
  # Keep physics, dt, and Gummel relaxation unchanged; accept that measured floor
  # with modest margin so the equal-time timestep comparison can complete.
  nl_abs_tol = 3.0e-7
  nl_max_its = 80
  automatic_scaling = false
  auto_advance = true
  fixed_point_min_its = 2
  fixed_point_max_its = @@FP_MAX@@
  fixed_point_rel_tol = 1.0e-8
  fixed_point_abs_tol = 1.0e-12
  accept_on_max_fixed_point_iteration = false
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  [step_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
    new_row_tolerance = 1.0e-30
  []
  [final_csv]
    type = CSV
    execute_on = 'FINAL'
  []
  [final_exodus]
    type = Exodus
    execute_on = 'FINAL'
  []
[]
