# Issue #234 bottom-up discriminator: 1D oxygen heavy flow + corrected diffusion
# + surface reactions, with no electric motion and no SEE.
#
# Gas: 10 mTorr = 1.33322 Pa, Tg = 300 K.
# Flow: solved 1D incompressible u-p system; no imposed pressure drop/flow, so u=0 baseline.
# Species: heavy advection + mass-average-corrected mixture diffusion + right-wall reactions.
# Electron: diffusion + right-wall thermal loss only.
# No Poisson, no electrostatic drift/migration, no volumetric chemistry, no SEE.

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

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'T_g p_gas T_e_K rho_const mu_const mean_en_eV electron_diffusion'
    prop_values = '300.0 1.33322 44350.61153766496 1.3793506167141378e-5 2.0e-5 5.73276 4.12573e4'
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
  [O2p_surface]
    type = ADParsedFunctorMaterial
    property_name = O2p_surface_mass_flux
    functor_names = 'rho_const w_O2p T_g'
    functor_symbols = 'rho w tg'
    expression = '0.25*sqrt(8.0*8.31446*tg/(pi*0.032))*rho*w'
  []
  [Om_surface]
    type = ADParsedFunctorMaterial
    property_name = Om_surface_mass_flux
    functor_names = 'rho_const w_Om T_g'
    functor_symbols = 'rho w tg'
    expression = '0.25*sqrt(8.0*8.31446*tg/(pi*0.016))*rho*w'
  []
  [Op_surface]
    type = ADParsedFunctorMaterial
    property_name = Op_surface_mass_flux
    functor_names = 'rho_const w_Op T_g'
    functor_symbols = 'rho w tg'
    expression = '0.25*sqrt(8.0*8.31446*tg/(pi*0.016))*rho*w'
  []

  [O_return]
    type = ADParsedFunctorMaterial
    property_name = O_return_mass_flux_inward
    functor_names = 'Op_surface_mass_flux Om_surface_mass_flux'
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
  [wall_u]
    type = INSFVNoSlipWallBC
    variable = u
    boundary = 'left right'
    function = 0
  []
  [outlet_p]
    type = INSFVOutletPressureBC
    variable = p
    boundary = right
    function = 1.33322
  []

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
  [O2p_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = right
    functor = O2p_surface_mass_flux
    factor = -1
  []
  [Om_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = right
    functor = Om_surface_mass_flux
    factor = -1
  []
  [Op_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = right
    functor = Op_surface_mass_flux
    factor = -1
  []
  [O_neutralization_return]
    type = FVFunctorNeumannBC
    variable = w_O
    boundary = right
    functor = O_return_mass_flux_inward
    factor = 1
  []

  [electron_thermal_loss]
    type = FVFunctorNeumannBC
    variable = log_e
    boundary = right
    functor = electron_thermal_flux_molar_outward
    factor = -1
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
  [electron_thermal_integral]
    type = TimeIntegratedPostprocessor
    value = electron_thermal_rate
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
    functor = O2p_surface_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_surface_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = Om_surface_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_surface_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = Op_surface_mass_flux
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
