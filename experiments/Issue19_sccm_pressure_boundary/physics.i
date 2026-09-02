# ==============================================================================
# R19 EVR #1 — conservative SCCM inlet + absolute-pressure outlet
# qvt.msh / mesh.i are fixed #18 canonical inputs.
# ==============================================================================
Q_sccm = 100
M_inlet = 0.032
Vm_std = 0.0224136
outlet_pressure = 1.33322
rho_const = 1.71e-05
mu_const = 2e-05

Q_std = ${fparse Q_sccm * 1e-6 / 60.0}
inlet_mdot_value = ${fparse Q_std * M_inlet / Vm_std}

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
[]

[FunctorMaterials]
  [flow_props]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_flow mu_flow'
    prop_values = '${rho_const} ${mu_const}'
    block = plasma
  []
[]

[FVKernels]
  [mass]
    type = INSFVMassAdvection
    variable = p
    rho = rho_flow
    block = plasma
  []

  [u_advection]
    type = INSFVMomentumAdvection
    variable = u
    rho = rho_flow
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
  [u_rz_viscous_source]
    type = INSFVMomentumViscousSourceRZ
    variable = u
    mu = mu_flow
    momentum_component = x
    block = plasma
  []

  [v_advection]
    type = INSFVMomentumAdvection
    variable = v
    rho = rho_flow
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
[]

[FVBCs]
  [inlet_mass]
    type = WCNSFVMassFluxBC
    variable = p
    boundary = inlet
    mdot_pp = inlet_mdot
    area_pp = inlet_area
    rho = rho_flow
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
    rho = rho_flow
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
    rho = rho_flow
    vel_x = u
    vel_y = v
    momentum_component = y
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
  [inlet_mass_actual]
    type = VolumetricFlowRate
    boundary = inlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_flow
    rhie_chow_user_object = rc
  []
  [outlet_mass_actual]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_flow
    rhie_chow_user_object = rc
  []
  [outlet_p_avg]
    type = SideAverageFunctorPostprocessor
    boundary = outlet
    functor = p
    restrict_to_functors_domain = true
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
  nl_max_its = 50
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
[]

[Outputs]
  csv = true
  execute_on = FINAL
[]
