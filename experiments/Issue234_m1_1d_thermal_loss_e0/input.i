# Issue #234 bottom-up discriminator: 1D log-molar electron thermal surface loss, E = 0.
# No Poisson, diffusion, chemistry, electron-energy solve, SEE, or RF/electrostatic heating.

[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 10
  xmin = 0.0
  xmax = 0.01
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [log_e]
    type = MooseVariableFVReal
    # n_e0 = 1e18 m^-3 -> c_e0 = n_e0/N_A mol/m^3
    initial_condition = -13.30836826905085
  []
[]

[Functions]
  [phi_zero]
    type = ParsedFunction
    expression = '0.0*x'
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en_eV electron_mobility carrier_one'
    prop_values = '5.73276 9750.0 1.0'
  []

  [electron_molar_density]
    type = ADParsedFunctorMaterial
    property_name = c_e_molar
    functor_names = 'log_e'
    functor_symbols = 'loge'
    expression = 'exp(loge)'
  []

  [electron_physical_density]
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
    # Pure isotropic-Maxwellian wall collection, no sheath suppression:
    # Gamma = (1/4) c_e * vbar_e,
    # vbar_e = sqrt(16 e <epsilon> / (3 pi m_e)), with <epsilon> in eV.
    expression = '0.25*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))'
  []
[]

[FVKernels]
  [electron_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_e
  []

  [electron_drift_zero_field]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_e
    potential = phi_zero
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
    # FVFunctorNeumannBC returns -factor*functor to the residual.
    # factor=-1 therefore contributes +Gamma_out to the conservative balance.
    factor = -1
  []
[]

[Postprocessors]
  [c_e_inventory_per_area]
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

  [wall_thermal_flux_rate_per_area]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = thermal_flux_molar_outward
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [wall_thermal_loss_integral_per_area]
    type = TimeIntegratedPostprocessor
    value = wall_thermal_flux_rate_per_area
    time_integration_scheme = 'implicit-euler'
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 1.0e-10
  end_time = 1.0e-9
  nl_rel_tol = 1.0e-10
  nl_abs_tol = 1.0e-14
  nl_max_its = 30
  automatic_scaling = false
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
