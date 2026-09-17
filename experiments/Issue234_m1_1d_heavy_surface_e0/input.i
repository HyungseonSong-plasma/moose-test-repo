# Issue #234 bottom-up discriminator: 1D oxygen heavy species + electron diffusion,
# surface reactions only, no electric motion.
#
# Gas: 10 mTorr = 1.33322 Pa, Tg = 300 K.
# No Poisson, no electrostatic drift/migration, no bulk chemistry, no flow.
# Right boundary only: heavy surface reactions, electron thermal loss, ion-induced SEE.

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
    # ne0 = 1e18 m^-3 -> ce0 = ne0/NA mol/m^3
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
    prop_names = 'T_g p_gas T_e_K rho_const mean_en_eV electron_diffusion'
    # rho_const is the ideal-gas initial mixture density for the frozen diagnostic composition.
    prop_values = '300.0 1.33322 44350.61153766496 1.3793506167141378e-5 5.73276 4.12573e4'
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

  [mobility_O2p]
    type = ADParsedFunctorMaterial
    property_name = mu_O2p
    functor_names = 'D_mix_O2p T_g'
    functor_symbols = 'd t'
    expression = '11604.518121550082*d/t'
  []
  [mobility_Om]
    type = ADParsedFunctorMaterial
    property_name = mu_Om
    functor_names = 'D_mix_Om T_g'
    functor_symbols = 'd t'
    expression = '11604.518121550082*d/t'
  []
  [mobility_Op]
    type = ADParsedFunctorMaterial
    property_name = mu_Op
    functor_names = 'D_mix_Op T_g'
    functor_symbols = 'd t'
    expression = '11604.518121550082*d/t'
  []

  # Neutral thermal surface-reaction mass fluxes, outward-positive [kg/m^2/s].
  # Accepted Issue #27 sticking coefficients: O=0.2, O2*=1, O*=0.2.
  [O_surface]
    type = ADParsedFunctorMaterial
    property_name = O_surface_mass_flux
    functor_names = 'rho_const w_O T_g'
    functor_symbols = 'rho w tg'
    expression = '0.2*0.25*sqrt(8.0*8.31446*tg/(pi*0.016))*rho*w'
  []
  [O2s_surface]
    type = ADParsedFunctorMaterial
    property_name = O2s_surface_mass_flux
    functor_names = 'rho_const w_O2s T_g'
    functor_symbols = 'rho w tg'
    expression = '1.0*0.25*sqrt(8.0*8.31446*tg/(pi*0.032))*rho*w'
  []
  [Os_surface]
    type = ADParsedFunctorMaterial
    property_name = Os_surface_mass_flux
    functor_names = 'rho_const w_Os T_g'
    functor_symbols = 'rho w tg'
    expression = '0.2*0.25*sqrt(8.0*8.31446*tg/(pi*0.016))*rho*w'
  []

  # Charged surface collection uses the accepted Issue #27 wall material.
  # potential is identically zero; migration output is not connected to any residual.
  [n_O2p]
    type = ADParsedFunctorMaterial
    property_name = n_O2p_m3
    functor_names = 'rho_const w_O2p'
    functor_symbols = 'rho w'
    expression = 'rho*w*6.02214076e23/0.032'
  []
  [n_Om]
    type = ADParsedFunctorMaterial
    property_name = n_Om_m3
    functor_names = 'rho_const w_Om'
    functor_symbols = 'rho w'
    expression = 'rho*w*6.02214076e23/0.016'
  []
  [n_Op]
    type = ADParsedFunctorMaterial
    property_name = n_Op_m3
    functor_names = 'rho_const w_Op'
    functor_symbols = 'rho w'
    expression = 'rho*w*6.02214076e23/0.016'
  []

  [O2p_wall]
    type = QPXIonWallFluxMaterial
    ion_number_density = n_O2p_m3
    potential = phi_zero
    mobility = mu_O2p
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.032
    sticking = 1.0
    declare_suffix = O2p
  []
  [Om_wall]
    type = QPXIonWallFluxMaterial
    ion_number_density = n_Om_m3
    potential = phi_zero
    mobility = mu_Om
    gas_temperature = T_g
    charge_number = -1
    molar_mass = 0.016
    sticking = 1.0
    declare_suffix = Om
  []
  [Op_wall]
    type = QPXIonWallFluxMaterial
    ion_number_density = n_Op_m3
    potential = phi_zero
    mobility = mu_Op
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.016
    sticking = 1.0
    declare_suffix = Op
  []

  # O+ and O- neutralize to O at the surface; equal mass is returned inward.
  [O_return]
    type = ADParsedFunctorMaterial
    property_name = O_return_mass_flux_inward
    functor_names = 'ion_surface_mass_flux_Op ion_surface_mass_flux_Om'
    functor_symbols = 'op om'
    expression = 'op+om'
  []

  [electron_thermal_surface]
    type = ADParsedFunctorMaterial
    property_name = electron_thermal_flux_molar_outward
    functor_names = 'log_e mean_en_eV'
    functor_symbols = 'loge mean_ev'
    expression = '0.25*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))'
  []

  # Ion-induced SEE: gamma_O2+ = gamma_O+ = 0.05. Migration is intentionally excluded.
  [electron_see]
    type = ADParsedFunctorMaterial
    property_name = electron_see_flux_molar_inward
    functor_names = 'ion_surface_mass_flux_O2p ion_surface_mass_flux_Op'
    functor_symbols = 'o2p op'
    expression = '0.05*(o2p/0.032+op/0.016)'
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
    diffusivity = electron_diffusion
  []

  [O2s_time]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w_O2s
    rho = rho_const
  []
  [O2s_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_O2s
    rho = rho_const
    diffusivity = D_mix_O2s
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []

  [O2p_time]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w_O2p
    rho = rho_const
  []
  [O2p_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_O2p
    rho = rho_const
    diffusivity = D_mix_O2p
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []

  [O_time]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w_O
    rho = rho_const
  []
  [O_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_O
    rho = rho_const
    diffusivity = D_mix_O
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []

  [Om_time]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w_Om
    rho = rho_const
  []
  [Om_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_Om
    rho = rho_const
    diffusivity = D_mix_Om
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []

  [Op_time]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w_Op
    rho = rho_const
  []
  [Op_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_Op
    rho = rho_const
    diffusivity = D_mix_Op
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []

  [Os_time]
    type = QPXFVConservativeMassFractionTimeDerivative
    variable = w_Os
    rho = rho_const
  []
  [Os_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_Os
    rho = rho_const
    diffusivity = D_mix_Os
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []
[]

[FVBCs]
  # Neutral surface losses. O2 products are represented through constrained O2.
  [O_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_O
    boundary = right
    functor = O_surface_mass_flux
    factor = -1
  []
  [O2s_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_O2s
    boundary = right
    functor = O2s_surface_mass_flux
    factor = -1
  []
  [Os_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_Os
    boundary = right
    functor = Os_surface_mass_flux
    factor = -1
  []

  # Charged surface losses. Only surface collection is connected; no migration/drift flux.
  [O2p_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = right
    functor = ion_surface_mass_flux_O2p
    factor = -1
  []
  [Om_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = right
    functor = ion_surface_mass_flux_Om
    factor = -1
  []
  [Op_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = right
    functor = ion_surface_mass_flux_Op
    factor = -1
  []

  # O+ and O- return as neutral O.
  [O_neutralization_return]
    type = FVFunctorNeumannBC
    variable = w_O
    boundary = right
    functor = O_return_mass_flux_inward
    factor = 1
  []

  # Electron random thermal loss and ion-induced secondary-electron source.
  [electron_thermal_loss]
    type = FVFunctorNeumannBC
    variable = log_e
    boundary = right
    functor = electron_thermal_flux_molar_outward
    factor = -1
  []
  [electron_see_source]
    type = FVFunctorNeumannBC
    variable = log_e
    boundary = right
    functor = electron_see_flux_molar_inward
    factor = 1
  []
[]

[Postprocessors]
  [electron_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = c_e_molar
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_thermal_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = electron_thermal_flux_molar_outward
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_see_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = electron_see_flux_molar_inward
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_thermal_integral]
    type = TimeIntegratedPostprocessor
    value = electron_thermal_rate
    time_integration_scheme = 'implicit-euler'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_see_integral]
    type = TimeIntegratedPostprocessor
    value = electron_see_rate
    time_integration_scheme = 'implicit-euler'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_see_energy_power]
    type = ScalePostprocessor
    value = electron_see_rate
    # mol/s * F[C/mol] * 4[V] = W, per unit transverse area in this 1D model.
    scaling_factor = 385941.32853494
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

  [O_surface_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = O_surface_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2s_surface_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = O2s_surface_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Os_surface_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = Os_surface_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_surface_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = ion_surface_mass_flux_O2p
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_surface_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = ion_surface_mass_flux_Om
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_surface_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = ion_surface_mass_flux_Op
    restrict_to_functors_domain = true
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
