# Issue #234 bottom-up discriminator: 1D electron electrostatic drift + controlled thermal wall loss.
# Prescribed phi(x)=100*x V gives E_x=-100 V/m and z_e=-1 drives electrons toward +x/right.
# Bulk drift owns interior transport; the right thermal BC owns boundary particle loss.
# No diffusion, Poisson, volumetric chemistry, electron-energy solve, SEE, or RF/electrostatic heating.

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
    # n_e0 = 1e18 m^-3 -> c_e0 = n_e0/N_A mol/m^3
    initial_condition = -13.30836826905085
  []
[]

[Functions]
  [phi_ramp]
    type = ParsedFunction
    expression = '100.0*x'
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en_eV electron_mobility carrier_one'
    prop_values = '5.73276 9755.114369721427 1.0'
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

  [electron_molar_x_moment]
    type = ADParsedFunctorMaterial
    property_name = c_e_x_moment
    functor_names = 'log_e'
    functor_symbols = 'loge'
    expression = 'x*exp(loge)'
  []

  [thermal_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = thermal_flux_molar_outward
    functor_names = 'log_e mean_en_eV'
    functor_symbols = 'loge mean_ev'
    # Pure isotropic-Maxwellian collection: Gamma=(1/4)c_e*vbar_e.
    expression = '0.25*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))'
  []
[]

[FVKernels]
  [electron_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_e
  []

  [electron_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_e
    potential = phi_ramp
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    # Boundary particle flux is owned exclusively by the explicit wall BC.
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

  [c_e_x_moment_per_area]
    type = ADElementIntegralFunctorPostprocessor
    functor = c_e_x_moment
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
  dt = 5.0e-11
  end_time = 5.0e-10
  nl_rel_tol = 1.0e-10
  nl_abs_tol = 1.0e-14
  nl_max_its = 30
  automatic_scaling = false
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]

[Outputs]
  csv = true
  exodus = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
