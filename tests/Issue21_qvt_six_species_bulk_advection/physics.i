# ==============================================================================
# R21 EVR1 — steady qvt six-species bulk-advection integration
#
# Production bridge under test:
#   real qvt flow + SCCM/pressure BC + six solved species + constrained O2
#   + density-weighted conservative advection + mixture-averaged diffusion
#
# EVR1 is deliberately STEADY: no species time derivative. This isolates
# qvt/flow/advection/diffusion/boundary wiring from the transient rho-dot issue.
# ==============================================================================
Q_sccm = 100
Vm_std = 0.0224136
outlet_pressure = 1.33322
T_g_value = 600
T_e_value = 20000
n_e_value = 1e+16
mu_const = 2e-05
Yin_O2 = 0.7
Yin_O2s = 0.05
Yin_O2p = 0.01
Yin_O = 0.1
Yin_Om = 0.01
Yin_Op = 0.01
Yin_Os = 0.12
M_inlet = ${fparse 1.0/(Yin_O2/0.032+Yin_O2s/0.032+Yin_O2p/0.032+Yin_O/0.016+Yin_Om/0.016+Yin_Op/0.016+Yin_Os/0.016)}
Q_std = ${fparse Q_sccm * 1e-6 / 60.0}
inlet_mdot_value = ${fparse Q_std * M_inlet / Vm_std}
inlet_mdot_O2s_value = ${fparse inlet_mdot_value * Yin_O2s}
inlet_mdot_O2p_value = ${fparse inlet_mdot_value * Yin_O2p}
inlet_mdot_O_value = ${fparse inlet_mdot_value * Yin_O}
inlet_mdot_Om_value = ${fparse inlet_mdot_value * Yin_Om}
inlet_mdot_Op_value = ${fparse inlet_mdot_value * Yin_Op}
inlet_mdot_Os_value = ${fparse inlet_mdot_value * Yin_Os}

[Problem]
  kernel_coverage_check = false
[]

[GlobalParams]
  rhie_chow_user_object = rc
  advected_interp_method = upwind
  velocity_interp_method = rc
  two_term_boundary_expansion = true
[]

[UserObjects]
  [rc]
    type = INSFVRhieChowInterpolator
    u = u
    v = v
    pressure = p
    block = plasma
  []
[]

[Variables]
  [u]
    type = INSFVVelocityVariable
    initial_condition = 0
    block = plasma
  []
  [v]
    type = INSFVVelocityVariable
    initial_condition = 0
    block = plasma
  []
  [p]
    type = INSFVPressureVariable
    initial_condition = ${outlet_pressure}
    block = plasma
  []
  [w_O2s]
    type = INSFVScalarFieldVariable
    initial_condition = ${Yin_O2s}
    block = plasma
  []
  [w_O2p]
    type = INSFVScalarFieldVariable
    initial_condition = ${Yin_O2p}
    block = plasma
  []
  [w_O]
    type = INSFVScalarFieldVariable
    initial_condition = ${Yin_O}
    block = plasma
  []
  [w_Om]
    type = INSFVScalarFieldVariable
    initial_condition = ${Yin_Om}
    block = plasma
  []
  [w_Op]
    type = INSFVScalarFieldVariable
    initial_condition = ${Yin_Op}
    block = plasma
  []
  [w_Os]
    type = INSFVScalarFieldVariable
    initial_condition = ${Yin_Os}
    block = plasma
  []
[]

[FunctorMaterials]
  [state_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'T_g T_e n_e mu_flow'
    prop_values = '${T_g_value} ${T_e_value} ${n_e_value} ${mu_const}'
    block = plasma
  []

  [O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 's1 s2 s3 s4 s5 s6'
    expression = '1.0-s1-s2-s3-s4-s5-s6'
    block = plasma
  []

  [mean_molar_mass]
    type = ADParsedFunctorMaterial
    property_name = Mn_mix
    functor_names = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 'm0 m1 m2 m3 m4 m5 m6'
    expression = '1.0/(m0/0.032+m1/0.032+m2/0.032+m3/0.016+m4/0.016+m5/0.016+m6/0.016)'
    block = plasma
  []

  [mixture_density]
    type = ADParsedFunctorMaterial
    property_name = rho_mat
    functor_names = 'p Mn_mix T_g'
    functor_symbols = 'prs mol tmp'
    expression = 'prs*mol/(8.31446*tmp)'
    block = plasma
  []

  [sum_w]
    type = ADParsedFunctorMaterial
    property_name = sum_w_functor
    functor_names = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 'q0 q1 q2 q3 q4 q5 q6'
    expression = 'q0+q1+q2+q3+q4+q5+q6'
    block = plasma
  []

  [rho_w_O2_material]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O2
    functor_names = 'rho_mat w_O2_constraint'
    functor_symbols = 'rho_s wf_s'
    expression = 'rho_s*wf_s'
    block = plasma
  []

  [rho_w_O2s_material]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O2s
    functor_names = 'rho_mat w_O2s'
    functor_symbols = 'rho_s wf_s'
    expression = 'rho_s*wf_s'
    block = plasma
  []

  [rho_w_O2p_material]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O2p
    functor_names = 'rho_mat w_O2p'
    functor_symbols = 'rho_s wf_s'
    expression = 'rho_s*wf_s'
    block = plasma
  []

  [rho_w_O_material]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O
    functor_names = 'rho_mat w_O'
    functor_symbols = 'rho_s wf_s'
    expression = 'rho_s*wf_s'
    block = plasma
  []

  [rho_w_Om_material]
    type = ADParsedFunctorMaterial
    property_name = rho_w_Om
    functor_names = 'rho_mat w_Om'
    functor_symbols = 'rho_s wf_s'
    expression = 'rho_s*wf_s'
    block = plasma
  []

  [rho_w_Op_material]
    type = ADParsedFunctorMaterial
    property_name = rho_w_Op
    functor_names = 'rho_mat w_Op'
    functor_symbols = 'rho_s wf_s'
    expression = 'rho_s*wf_s'
    block = plasma
  []

  [rho_w_Os_material]
    type = ADParsedFunctorMaterial
    property_name = rho_w_Os
    functor_names = 'rho_mat w_Os'
    functor_symbols = 'rho_s wf_s'
    expression = 'rho_s*wf_s'
    block = plasma
  []

  [heavy_transport]
    type = QPXThermalDiffusionMaterial
    temperature = T_g
    pressure = p
    electron_temperature = T_e
    electron_number_density = n_e
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    D_T_names = 'D_T_O2 D_T_O2s D_T_O2p D_T_O D_T_Om D_T_Op D_T_Os'
    kT_names = 'kT_O2 kT_O2s kT_O2p kT_O kT_Om kT_Op kT_Os'
    block = plasma
  []
[]

[FVKernels]
  [mass]
    type = INSFVMassAdvection
    variable = p
    rho = rho_mat
    block = plasma
  []
  [u_advection]
    type = INSFVMomentumAdvection
    variable = u
    rho = rho_mat
    momentum_component = x
    block = plasma
  []
  [u_diffusion]
    type = INSFVMomentumDiffusion
    variable = u
    mu = mu_flow
    momentum_component = x
    block = plasma
  []
  [u_pressure]
    type = INSFVMomentumPressure
    variable = u
    pressure = p
    momentum_component = x
    block = plasma
  []
  [v_advection]
    type = INSFVMomentumAdvection
    variable = v
    rho = rho_mat
    momentum_component = y
    block = plasma
  []
  [v_diffusion]
    type = INSFVMomentumDiffusion
    variable = v
    mu = mu_flow
    momentum_component = y
    block = plasma
  []
  [v_pressure]
    type = INSFVMomentumPressure
    variable = v
    pressure = p
    momentum_component = y
    block = plasma
  []
  [u_rz_viscous_source]
    type = INSFVMomentumViscousSourceRZ
    variable = u
    mu = mu_flow
    momentum_component = x
    block = plasma
  []

  [O2s_advection]
    type = QPXFVMassFractionAdvection
    variable = w_O2s
    rho = rho_mat
    block = plasma
  []
  [O2s_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_O2s
    rho = rho_mat
    diffusivity = D_mix_O2s
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []

  [O2p_advection]
    type = QPXFVMassFractionAdvection
    variable = w_O2p
    rho = rho_mat
    block = plasma
  []
  [O2p_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_O2p
    rho = rho_mat
    diffusivity = D_mix_O2p
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []

  [O_advection]
    type = QPXFVMassFractionAdvection
    variable = w_O
    rho = rho_mat
    block = plasma
  []
  [O_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_O
    rho = rho_mat
    diffusivity = D_mix_O
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []

  [Om_advection]
    type = QPXFVMassFractionAdvection
    variable = w_Om
    rho = rho_mat
    block = plasma
  []
  [Om_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_Om
    rho = rho_mat
    diffusivity = D_mix_Om
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []

  [Op_advection]
    type = QPXFVMassFractionAdvection
    variable = w_Op
    rho = rho_mat
    block = plasma
  []
  [Op_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_Op
    rho = rho_mat
    diffusivity = D_mix_Op
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []

  [Os_advection]
    type = QPXFVMassFractionAdvection
    variable = w_Os
    rho = rho_mat
    block = plasma
  []
  [Os_diffusion]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_Os
    rho = rho_mat
    diffusivity = D_mix_Os
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []
[]

[FVBCs]
  [inlet_mass]
    type = WCNSFVMassFluxBC
    variable = p
    boundary = inlet
    mdot_pp = inlet_mdot
    area_pp = inlet_area
    rho = rho_mat
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []
  [inlet_u]
    type = WCNSFVMomentumFluxBC
    variable = u
    boundary = inlet
    mdot_pp = inlet_mdot
    area_pp = inlet_area
    rho = rho_mat
    vel_x = u
    vel_y = v
    momentum_component = x
    direction = '-1 0 0'
  []
  [inlet_v]
    type = WCNSFVMomentumFluxBC
    variable = v
    boundary = inlet
    mdot_pp = inlet_mdot
    area_pp = inlet_area
    rho = rho_mat
    vel_x = u
    vel_y = v
    momentum_component = y
    direction = '-1 0 0'
  []

  [inlet_O2s]
    type = WCNSFVScalarFluxBC
    variable = w_O2s
    boundary = inlet
    passive_scalar = w_O2s
    scalar_flux_pp = inlet_mdot_O2s
    area_pp = inlet_area
    rho = rho_mat
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []

  [inlet_O2p]
    type = WCNSFVScalarFluxBC
    variable = w_O2p
    boundary = inlet
    passive_scalar = w_O2p
    scalar_flux_pp = inlet_mdot_O2p
    area_pp = inlet_area
    rho = rho_mat
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []

  [inlet_O]
    type = WCNSFVScalarFluxBC
    variable = w_O
    boundary = inlet
    passive_scalar = w_O
    scalar_flux_pp = inlet_mdot_O
    area_pp = inlet_area
    rho = rho_mat
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []

  [inlet_Om]
    type = WCNSFVScalarFluxBC
    variable = w_Om
    boundary = inlet
    passive_scalar = w_Om
    scalar_flux_pp = inlet_mdot_Om
    area_pp = inlet_area
    rho = rho_mat
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []

  [inlet_Op]
    type = WCNSFVScalarFluxBC
    variable = w_Op
    boundary = inlet
    passive_scalar = w_Op
    scalar_flux_pp = inlet_mdot_Op
    area_pp = inlet_area
    rho = rho_mat
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []

  [inlet_Os]
    type = WCNSFVScalarFluxBC
    variable = w_Os
    boundary = inlet
    passive_scalar = w_Os
    scalar_flux_pp = inlet_mdot_Os
    area_pp = inlet_area
    rho = rho_mat
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []

  [wall_u]
    type = INSFVNoSlipWallBC
    variable = u
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    function = 0
  []
  [wall_v]
    type = INSFVNoSlipWallBC
    variable = v
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    function = 0
  []
  [outlet_p]
    type = INSFVOutletPressureBC
    variable = p
    boundary = outlet
    function = ${outlet_pressure}
  []
[]

[Postprocessors]
  [inlet_area]
    type = AreaPostprocessor
    boundary = inlet
    execute_on = INITIAL
  []
  [inlet_mdot]
    type = Receiver
    default = ${inlet_mdot_value}
  []
  [inlet_mdot_O2s]
    type = Receiver
    default = ${inlet_mdot_O2s_value}
  []
  [inlet_mdot_O2p]
    type = Receiver
    default = ${inlet_mdot_O2p_value}
  []
  [inlet_mdot_O]
    type = Receiver
    default = ${inlet_mdot_O_value}
  []
  [inlet_mdot_Om]
    type = Receiver
    default = ${inlet_mdot_Om_value}
  []
  [inlet_mdot_Op]
    type = Receiver
    default = ${inlet_mdot_Op_value}
  []
  [inlet_mdot_Os]
    type = Receiver
    default = ${inlet_mdot_Os_value}
  []
  [outlet_mass_actual]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_mat
    rhie_chow_user_object = rc
  []
  [outlet_p_avg]
    type = SideAverageFunctorPostprocessor
    boundary = outlet
    functor = p
    restrict_to_functors_domain = true
  []
  [w_O2_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2_constraint
    block = plasma
  []
  [w_O2_min]
    type = ADElementExtremeFunctorValue
    functor = w_O2_constraint
    value_type = min
    block = plasma
  []
  [w_O2_max]
    type = ADElementExtremeFunctorValue
    functor = w_O2_constraint
    value_type = max
    block = plasma
  []
  [Dmix_O2_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O2
    block = plasma
  []
  [outlet_mdot_O2]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_O2
    rhie_chow_user_object = rc
  []
  [w_O2s_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2s
    block = plasma
  []
  [w_O2s_min]
    type = ADElementExtremeFunctorValue
    functor = w_O2s
    value_type = min
    block = plasma
  []
  [w_O2s_max]
    type = ADElementExtremeFunctorValue
    functor = w_O2s
    value_type = max
    block = plasma
  []
  [Dmix_O2s_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O2s
    block = plasma
  []
  [outlet_mdot_O2s]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_O2s
    rhie_chow_user_object = rc
  []
  [w_O2p_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2p
    block = plasma
  []
  [w_O2p_min]
    type = ADElementExtremeFunctorValue
    functor = w_O2p
    value_type = min
    block = plasma
  []
  [w_O2p_max]
    type = ADElementExtremeFunctorValue
    functor = w_O2p
    value_type = max
    block = plasma
  []
  [Dmix_O2p_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O2p
    block = plasma
  []
  [outlet_mdot_O2p]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_O2p
    rhie_chow_user_object = rc
  []
  [w_O_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O
    block = plasma
  []
  [w_O_min]
    type = ADElementExtremeFunctorValue
    functor = w_O
    value_type = min
    block = plasma
  []
  [w_O_max]
    type = ADElementExtremeFunctorValue
    functor = w_O
    value_type = max
    block = plasma
  []
  [Dmix_O_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O
    block = plasma
  []
  [outlet_mdot_O]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_O
    rhie_chow_user_object = rc
  []
  [w_Om_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_Om
    block = plasma
  []
  [w_Om_min]
    type = ADElementExtremeFunctorValue
    functor = w_Om
    value_type = min
    block = plasma
  []
  [w_Om_max]
    type = ADElementExtremeFunctorValue
    functor = w_Om
    value_type = max
    block = plasma
  []
  [Dmix_Om_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_Om
    block = plasma
  []
  [outlet_mdot_Om]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_Om
    rhie_chow_user_object = rc
  []
  [w_Op_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_Op
    block = plasma
  []
  [w_Op_min]
    type = ADElementExtremeFunctorValue
    functor = w_Op
    value_type = min
    block = plasma
  []
  [w_Op_max]
    type = ADElementExtremeFunctorValue
    functor = w_Op
    value_type = max
    block = plasma
  []
  [Dmix_Op_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_Op
    block = plasma
  []
  [outlet_mdot_Op]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_Op
    rhie_chow_user_object = rc
  []
  [w_Os_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_Os
    block = plasma
  []
  [w_Os_min]
    type = ADElementExtremeFunctorValue
    functor = w_Os
    value_type = min
    block = plasma
  []
  [w_Os_max]
    type = ADElementExtremeFunctorValue
    functor = w_Os
    value_type = max
    block = plasma
  []
  [Dmix_Os_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_Os
    block = plasma
  []
  [outlet_mdot_Os]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_Os
    rhie_chow_user_object = rc
  []
  [sum_w_min]
    type = ADElementExtremeFunctorValue
    functor = sum_w_functor
    value_type = min
    block = plasma
  []
  [sum_w_max]
    type = ADElementExtremeFunctorValue
    functor = sum_w_functor
    value_type = max
    block = plasma
  []
  [Mn_avg]
    type = ElementAverageFunctorPostprocessor
    functor = Mn_mix
    block = plasma
  []
  [rho_avg]
    type = ElementAverageFunctorPostprocessor
    functor = rho_mat
    block = plasma
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
  line_search = none
  nl_rel_tol = 1e-9
  nl_abs_tol = 1e-11
  nl_max_its = 80
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
[]

[Outputs]
  csv = true
  execute_on = FINAL
[]
