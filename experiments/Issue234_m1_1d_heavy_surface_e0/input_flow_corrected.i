# Issue #234 bottom-up discriminator: independent electron wall-loss transport
# plus 1D oxygen heavy flow with corrected diffusion, E = 0 and no SEE.
#
# Gas: chamber pressure 10 mTorr = 1.33322 Pa, Tg = 300 K.
# Heavy flow: right pure-O2 20 sccm inlet, left absolute-pressure outlet at chamber pressure.
# Heavy species: gas advection + mass-average-corrected mixture diffusion.
# Electron: previous E=0 diffusion + pure thermal right-wall loss contract; no gas-flow advection.
# No Poisson, no volumetric chemistry, no SEE, no nonzero electric drift/migration.

Q_sccm = 20
M_inlet = 0.032
Vm_std = 0.0224136
outlet_pressure = 1.33322
Q_std = ${fparse Q_sccm * 1e-6 / 60.0}
inlet_mdot_value = ${fparse Q_std * M_inlet / Vm_std}

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

[GlobalParams]
  rhie_chow_user_object = rc
  advected_interp_method = upwind
  velocity_interp_method = rc
[]

[UserObjects]
  [rc]
    type = INSFVRhieChowInterpolator
    u = u
    pressure = p
  []
[]

[Variables]
  [u]
    type = INSFVVelocityVariable
    initial_condition = 0.0
  []
  [p]
    type = INSFVPressureVariable
    initial_condition = 1.33322
  []
  [log_e]
    type = MooseVariableFVReal
    # n_e0 = 1e18 m^-3 -> c_e0 = n_e0/N_A mol/m^3
    initial_condition = -13.30836826905085
  []
  [w_O2s]
    type = MooseVariableFVReal
    initial_condition = 0.05
  []
  [w_O2p]
    type = MooseVariableFVReal
    initial_condition = 0.01
  []
  [w_O]
    type = MooseVariableFVReal
    initial_condition = 0.10
  []
  [w_Om]
    type = MooseVariableFVReal
    initial_condition = 0.01
  []
  [w_Op]
    type = MooseVariableFVReal
    initial_condition = 0.01
  []
  [w_Os]
    type = MooseVariableFVReal
    initial_condition = 0.12
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
    prop_names = 'T_g p_gas T_e_K rho_const mu_const mean_en_eV electron_mobility electron_diffusion carrier_one'
    prop_values = '300.0 1.33322 44350.61153766496 1.3793506167141378e-5 2.0e-5 5.73276 9755.114369721427 41257.29899041419 1.0'
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
    # Previous pure isotropic-Maxwellian electron wall collection, no sheath suppression.
    expression = '0.25*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))'
  []

  [O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2
    functor_names = 'w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 's1 s2 s3 s4 s5 s6'
    expression = '1.0-s1-s2-s3-s4-s5-s6'
  []

  [mean_molar_mass]
    type = ADParsedFunctorMaterial
    property_name = Mn_mix
    functor_names = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 'm0 m1 m2 m3 m4 m5 m6'
    expression = '1.0/(m0/0.032+m1/0.032+m2/0.032+m3/0.016+m4/0.016+m5/0.016+m6/0.016)'
  []

  [sum_w]
    type = ADParsedFunctorMaterial
    property_name = sum_w_functor
    functor_names = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 'q0 q1 q2 q3 q4 q5 q6'
    expression = 'q0+q1+q2+q3+q4+q5+q6'
  []

  [heavy_transport]
    type = PhysicsThermalDiffusionMaterial
    temperature = T_g
    pressure = p_gas
    electron_temperature = T_e_K
    electron_number_density = electron_density_m3
    transport_data_file = '../Issue91_real_qvt_r3/r3_e0/transport_data.txt'
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    D_T_names = 'D_T_O2 D_T_O2s D_T_O2p D_T_O D_T_Om D_T_Op D_T_Os'
    kT_names = 'kT_O2 kT_O2s kT_O2p kT_O kT_Om kT_Op kT_Os'
  []
[]

[FVKernels]
  [mass]
    type = INSFVMassAdvection
    variable = p
    rho = rho_const
  []
  [u_advection]
    type = INSFVMomentumAdvection
    variable = u
    rho = rho_const
    momentum_component = x
  []
  [u_diffusion]
    type = INSFVMomentumDiffusion
    variable = u
    mu = mu_const
    momentum_component = x
  []
  [u_pressure]
    type = INSFVMomentumPressure
    variable = u
    pressure = p
    momentum_component = x
  []

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

  [O2s_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_O2s
    rho = rho_const
  []
  [O2s_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_O2s
    rho = rho_const
  []
  [O2s_diffusion]
    type = PhysicsFVHeavyMassCorrectedDiffusion
    variable = w_O2s
    rho = rho_const
    mean_molar_mass = Mn_mix
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    diffusivities = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    species_index = 1
  []

  [O2p_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_O2p
    rho = rho_const
  []
  [O2p_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_O2p
    rho = rho_const
  []
  [O2p_diffusion]
    type = PhysicsFVHeavyMassCorrectedDiffusion
    variable = w_O2p
    rho = rho_const
    mean_molar_mass = Mn_mix
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    diffusivities = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    species_index = 2
  []

  [O_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_O
    rho = rho_const
  []
  [O_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_O
    rho = rho_const
  []
  [O_diffusion]
    type = PhysicsFVHeavyMassCorrectedDiffusion
    variable = w_O
    rho = rho_const
    mean_molar_mass = Mn_mix
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    diffusivities = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    species_index = 3
  []

  [Om_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_Om
    rho = rho_const
  []
  [Om_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_Om
    rho = rho_const
  []
  [Om_diffusion]
    type = PhysicsFVHeavyMassCorrectedDiffusion
    variable = w_Om
    rho = rho_const
    mean_molar_mass = Mn_mix
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    diffusivities = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    species_index = 4
  []

  [Op_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_Op
    rho = rho_const
  []
  [Op_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_Op
    rho = rho_const
  []
  [Op_diffusion]
    type = PhysicsFVHeavyMassCorrectedDiffusion
    variable = w_Op
    rho = rho_const
    mean_molar_mass = Mn_mix
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    diffusivities = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    species_index = 5
  []

  [Os_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_Os
    rho = rho_const
  []
  [Os_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_Os
    rho = rho_const
  []
  [Os_diffusion]
    type = PhysicsFVHeavyMassCorrectedDiffusion
    variable = w_Os
    rho = rho_const
    mean_molar_mass = Mn_mix
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    diffusivities = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    species_index = 6
  []
[]

[FVBCs]
  # Heavy-flow inlet/outlet conditions and electron wall collection are intentionally
  # separate variable contracts even though they share the same 1D right boundary.
  [inlet_mass]
    type = WCNSFVMassFluxBC
    variable = p
    boundary = right
    mdot_pp = inlet_mdot
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    direction = '-1 0 0'
  []
  [inlet_u]
    type = WCNSFVMomentumFluxBC
    variable = u
    boundary = right
    mdot_pp = inlet_mdot
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    momentum_component = x
    direction = '-1 0 0'
  []

  [inlet_O2s]
    type = WCNSFVScalarFluxBC
    variable = w_O2s
    boundary = right
    passive_scalar = w_O2s
    scalar_flux_pp = inlet_mdot_O2s
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    direction = '-1 0 0'
  []
  [inlet_O2p]
    type = WCNSFVScalarFluxBC
    variable = w_O2p
    boundary = right
    passive_scalar = w_O2p
    scalar_flux_pp = inlet_mdot_O2p
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    direction = '-1 0 0'
  []
  [inlet_O]
    type = WCNSFVScalarFluxBC
    variable = w_O
    boundary = right
    passive_scalar = w_O
    scalar_flux_pp = inlet_mdot_O
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    direction = '-1 0 0'
  []
  [inlet_Om]
    type = WCNSFVScalarFluxBC
    variable = w_Om
    boundary = right
    passive_scalar = w_Om
    scalar_flux_pp = inlet_mdot_Om
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    direction = '-1 0 0'
  []
  [inlet_Op]
    type = WCNSFVScalarFluxBC
    variable = w_Op
    boundary = right
    passive_scalar = w_Op
    scalar_flux_pp = inlet_mdot_Op
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    direction = '-1 0 0'
  []
  [inlet_Os]
    type = WCNSFVScalarFluxBC
    variable = w_Os
    boundary = right
    passive_scalar = w_Os
    scalar_flux_pp = inlet_mdot_Os
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    direction = '-1 0 0'
  []

  [outlet_p]
    type = INSFVOutletPressureBC
    variable = p
    boundary = left
    function = ${outlet_pressure}
  []

  [right_thermal_surface_loss]
    type = FVFunctorNeumannBC
    variable = log_e
    boundary = right
    functor = thermal_flux_molar_outward
    factor = -1
  []
[]

[Postprocessors]
  [inlet_area]
    type = AreaPostprocessor
    boundary = right
    execute_on = INITIAL
  []
  [inlet_mdot]
    type = Receiver
    default = ${inlet_mdot_value}
  []
  [inlet_mdot_O2s]
    type = Receiver
    default = 0
  []
  [inlet_mdot_O2p]
    type = Receiver
    default = 0
  []
  [inlet_mdot_O]
    type = Receiver
    default = 0
  []
  [inlet_mdot_Om]
    type = Receiver
    default = 0
  []
  [inlet_mdot_Op]
    type = Receiver
    default = 0
  []
  [inlet_mdot_Os]
    type = Receiver
    default = 0
  []

  [inlet_mass_actual]
    type = VolumetricFlowRate
    boundary = right
    vel_x = u
    advected_quantity = rho_const
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [outlet_mass_actual]
    type = VolumetricFlowRate
    boundary = left
    vel_x = u
    advected_quantity = rho_const
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [outlet_p_avg]
    type = SideAverageFunctorPostprocessor
    boundary = left
    functor = p
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []

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

  [sum_w_min]
    type = ADElementExtremeFunctorValue
    functor = sum_w_functor
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sum_w_max]
    type = ADElementExtremeFunctorValue
    functor = sum_w_functor
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2_min]
    type = ADElementExtremeFunctorValue
    functor = w_O2
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [u_min]
    type = ADElementExtremeFunctorValue
    functor = u
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [u_max]
    type = ADElementExtremeFunctorValue
    functor = u
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [p_min]
    type = ADElementExtremeFunctorValue
    functor = p
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [p_max]
    type = ADElementExtremeFunctorValue
    functor = p
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 1.0e-10
  end_time = 1.0e-8
  nl_rel_tol = 1.0e-9
  nl_abs_tol = 1.0e-13
  nl_max_its = 50
  automatic_scaling = false
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  csv = true
  exodus = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
