[Mesh]
  coord_type = RZ
  rz_coord_axis = Y

  [main]
    type = FileMeshGenerator
    file = 'qvt.msh'
  []
  [inlet]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = port
    new_boundary = inlet
    input = main
  []
  [outlet]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = bottom
    new_boundary = outlet
    input = inlet
  []
  [plasma_electrode]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = electrode
    new_boundary = plasma_electrode
    input = outlet
  []
  [plasma_metal]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = metal
    new_boundary = plasma_metal
    input = plasma_electrode
  []
  [plasma_right]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = right
    new_boundary = plasma_right
    input = plasma_metal
  []
  [plasma_cover]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = cover
    new_boundary = plasma_cover
    input = plasma_right
  []
  [plasma_wafer]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = wafer
    new_boundary = plasma_wafer
    input = plasma_cover
  []
  [plasma_focus_ring]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = focus_ring
    new_boundary = plasma_focus_ring
    input = plasma_wafer
  []
  [plasma_only]
    type = BlockDeletionGenerator
    input = plasma_focus_ring
    operation = keep
    block = plasma
  []
[]

# ==============================================================================
# R15 EVR3 — canonical real-qvt charged-heavy migration + zero-net-mass-flux correction
#
# Accepted #21 steady bridge is retained:
#   real qvt flow + SCCM/pressure BC + six solved species + constrained O2
#   + density-weighted conservative advection + mixture-averaged diffusion
#
# New #22 production mechanism:
#   QPXFVConservativeMassFractionTimeDerivative
#     [(rho*w)^n - (rho*w)^(n-1)] / dt
#
# Q-1 transient closure also requires mixture continuity. The flow continuity
# equation therefore receives the built-in WCNSFVMassTimeDerivative using the
# already-validated continuous chain-rule drho/dt path. Momentum remains
# quasi-steady in each time slice; #22 owns species accumulation, not a new
# fully-transient momentum model.
# ==============================================================================
Q_sccm = 20
Vm_std = 0.0224136
outlet_pressure = 1.333223684
T_g_value = 300
mu_const = 2e-05
e_over_kB_K_per_V = 11604.518121550082
Yin_O2 = 0.99994000000000005
Yin_O2s = 1.0000000000000001e-05
Yin_O2p = 1.0000000000000001e-05
Yin_O = 1.0000000000000001e-05
Yin_Om = 1.0000000000000001e-05
Yin_Op = 1.0000000000000001e-05
Yin_Os = 1.0000000000000001e-05
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
    initial_condition = 1.0000000000000001e-05
    block = plasma
  []
  [w_O2p]
    type = INSFVScalarFieldVariable
    initial_condition = 1.0000000000000001e-05
    block = plasma
  []
  [w_O]
    type = INSFVScalarFieldVariable
    block = plasma
  initial_condition = 1.0000000000000001e-05
  []
  [w_Om]
    type = INSFVScalarFieldVariable
    initial_condition = 1.0000000000000001e-05
    block = plasma
  []
  [w_Op]
    type = INSFVScalarFieldVariable
    initial_condition = 1.0000000000000001e-05
    block = plasma
  []
  [w_Os]
    type = INSFVScalarFieldVariable
    initial_condition = 1.0000000000000001e-05
    block = plasma
  []
[]


[Functions]

  # Prescribed field only for #15 promotion. Poisson feedback belongs to #16.
  # E = -grad(phi) = +E0_migration e_x.
[]

[ICs]
[]

[FunctorMaterials]
  [state_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'T_g mu_flow'
    prop_values = '${T_g_value} ${mu_const}'
    block = plasma
  []


  # Direct solver-variable dot functors used only by WCNSFV mixture continuity.
  # GenericFunctorMaterial generates dp_state_dt, dwO_state_dt, ... from
  # the active time integrator.
  [transient_state_dot_aliases]
    type = ADGenericFunctorMaterial
    prop_names = 'p_state wO_state wOm_state wOp_state wOs_state'
    prop_values = 'p w_O w_Om w_Op w_Os'
    define_dot_functors = true
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


  # For this oxygen set, O2/O2s/O2p all have M=0.032 kg/mol and
  # O/Om/Op/Os all have M=0.016 kg/mol. With Q-1 closure:
  #   Mn = 0.032 / (1 + A), A=w_O+w_Om+w_Op+w_Os
  # so dMn/dt = -31.25*Mn^2*dA/dt.
  [mean_molar_mass_dot]
    type = ADParsedFunctorMaterial
    property_name = dMn_dt_model
    functor_names = 'Mn_mix dwO_state_dt dwOm_state_dt dwOp_state_dt dwOs_state_dt'
    functor_symbols = 'mnv dwo dwom dwop dwos'
    expression = '-31.25*mnv*mnv*(dwo+dwom+dwop+dwos)'
    block = plasma
  []

  # T_g is fixed in #22. rho = p*Mn/(R*T), therefore
  # drho/dt = [Mn*dp/dt + p*dMn/dt]/(R*T).
  [mixture_density_dot]
    type = ADParsedFunctorMaterial
    property_name = drho_dt_model
    functor_names = 'p Mn_mix dp_state_dt dMn_dt_model T_g'
    functor_symbols = 'prv mnv dpv dmnv tgv'
    expression = '(mnv*dpv+prv*dmnv)/(8.31446*tgv)'
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
    type = PhysicsThermalDiffusionMaterial
    temperature = T_g
    pressure = p
    electron_temperature = T_e_from_gummel_K
    electron_number_density = electron_density_from_gummel
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    D_T_names = 'D_T_O2 D_T_O2s D_T_O2p D_T_O D_T_Om D_T_Op D_T_Os'
    kT_names = 'kT_O2 kT_O2s kT_O2p kT_O kT_Om kT_Op kT_Os'
    block = plasma
  []

  # Mixture-averaged ion mobility, COMSOL-compatible default:
  #   mu_k = e * D_mix,k / (k_B * T_ion), with T_ion = T_g.
  # Mobility is a positive magnitude; charge sign is owned by charge_number / ion_charges.
  [mobility_O2p]
    type = ADParsedFunctorMaterial
    property_name = mu_O2p
    functor_names = 'D_mix_O2p T_g'
    functor_symbols = 'dcoef tgas'
    expression = '${e_over_kB_K_per_V}*dcoef/tgas'
    block = plasma
  []
  [mobility_Om]
    type = ADParsedFunctorMaterial
    property_name = mu_Om
    functor_names = 'D_mix_Om T_g'
    functor_symbols = 'dcoef tgas'
    expression = '${e_over_kB_K_per_V}*dcoef/tgas'
    block = plasma
  []
  [mobility_Op]
    type = ADParsedFunctorMaterial
    property_name = mu_Op
    functor_names = 'D_mix_Op T_g'
    functor_symbols = 'dcoef tgas'
    expression = '${e_over_kB_K_per_V}*dcoef/tgas'
    block = plasma
  []
  [electron_temperature_from_mean_energy]
    type = ADParsedFunctorMaterial
    property_name = T_e_from_gummel_K
    functor_names = 'mean_energy_from_gummel'
    functor_symbols = 'mean_ev'
    expression = '7736.3454143667204*mean_ev'
    block = plasma
  []
  [O_wall_flux_material]
    type = ADParsedFunctorMaterial
    property_name = O_wall_flux_outward
    functor_names = 'rho_mat w_O T_g'
    functor_symbols = 'rho o tg'
    expression = '0.20000000000000001*0.25*sqrt(8.0*8.3144600000000004*tg/(3.14159265358979323846*0.016))*rho*o'
    block = plasma
  []
  [O2s_wall_flux_material]
    type = ADParsedFunctorMaterial
    property_name = O2s_wall_flux_outward
    functor_names = 'rho_mat w_O2s T_g'
    functor_symbols = 'rho o2s tg'
    expression = '1*0.25*sqrt(8.0*8.3144600000000004*tg/(3.14159265358979323846*0.032000000000000001))*rho*o2s'
    block = plasma
  []
  [Os_wall_flux_material]
    type = ADParsedFunctorMaterial
    property_name = Os_wall_flux_outward
    functor_names = 'rho_mat w_Os T_g'
    functor_symbols = 'rho os tg'
    expression = '0.20000000000000001*0.25*sqrt(8.0*8.3144600000000004*tg/(3.14159265358979323846*0.016))*rho*os'
    block = plasma
  []
  [O2p_number_density]
    type = ADParsedFunctorMaterial
    property_name = number_density_O2p
    functor_names = 'rho_mat w_O2p'
    functor_symbols = 'rho w'
    expression = 'rho*w*6.0221407599999999e+23/0.032000000000000001'
    block = plasma
  []
  [O2p_wall_flux]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = number_density_O2p
    potential = potential_from_gummel
    mobility = mu_O2p
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.032000000000000001
    sticking = 1
    declare_suffix = O2p
    block = plasma
  []
  [Om_number_density]
    type = ADParsedFunctorMaterial
    property_name = number_density_Om
    functor_names = 'rho_mat w_Om'
    functor_symbols = 'rho w'
    expression = 'rho*w*6.0221407599999999e+23/0.016'
    block = plasma
  []
  [Om_wall_flux]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = number_density_Om
    potential = potential_from_gummel
    mobility = mu_Om
    gas_temperature = T_g
    charge_number = -1
    molar_mass = 0.016
    sticking = 1
    declare_suffix = Om
    block = plasma
  []
  [Op_number_density]
    type = ADParsedFunctorMaterial
    property_name = number_density_Op
    functor_names = 'rho_mat w_Op'
    functor_symbols = 'rho w'
    expression = 'rho*w*6.0221407599999999e+23/0.016'
    block = plasma
  []
  [Op_wall_flux]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = number_density_Op
    potential = potential_from_gummel
    mobility = mu_Op
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.016
    sticking = 1
    declare_suffix = Op
    block = plasma
  []
  [ion_neutralization_O_return_material]
    type = ADParsedFunctorMaterial
    property_name = ion_neutralization_O_return_mass_flux_inward
    functor_names = 'ion_surface_mass_flux_Op ion_migration_mass_flux_Op ion_surface_mass_flux_Om ion_migration_mass_flux_Om'
    functor_symbols = 'sop mop som mom'
    expression = 'sop+mop+som+mom'
    block = plasma
  []
[]

[FVKernels]
  [mass_time]
    type = WCNSFVMassTimeDerivative
    variable = p
    drho_dt = drho_dt_model
    block = plasma
  []
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

  [O2s_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_O2s
    rho = rho_mat
    block = plasma
  []
  [O2s_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_O2s
    rho = rho_mat
    block = plasma
  []
  [O2s_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_O2s
    rho = rho_mat
    diffusivity = D_mix_O2s
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []

  [O2p_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_O2p
    rho = rho_mat
    block = plasma
  []
  [O2p_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_O2p
    rho = rho_mat
    block = plasma
  []
  [O2p_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_O2p
    rho = rho_mat
    diffusivity = D_mix_O2p
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []

  [O_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_O
    rho = rho_mat
    block = plasma
  []
  [O_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_O
    rho = rho_mat
    block = plasma
  []
  [O_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_O
    rho = rho_mat
    diffusivity = D_mix_O
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []

  [Om_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_Om
    rho = rho_mat
    block = plasma
  []
  [Om_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_Om
    rho = rho_mat
    block = plasma
  []
  [Om_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_Om
    rho = rho_mat
    diffusivity = D_mix_Om
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []

  [Op_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_Op
    rho = rho_mat
    block = plasma
  []
  [Op_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_Op
    rho = rho_mat
    block = plasma
  []
  [Op_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_Op
    rho = rho_mat
    diffusivity = D_mix_Op
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []

  [Os_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_Os
    rho = rho_mat
    block = plasma
  []
  [Os_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_Os
    rho = rho_mat
    block = plasma
  []
  [Os_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_Os
    rho = rho_mat
    diffusivity = D_mix_Os
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
    block = plasma
  []
  [O2p_electrostatic_drift]
    type = PhysicsFVElectrostaticDrift
    variable = w_O2p
    potential = potential_from_gummel
    mobility = mu_O2p
    carrier = rho_mat
    charge_number = 1
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []

  [Om_electrostatic_drift]
    type = PhysicsFVElectrostaticDrift
    variable = w_Om
    potential = potential_from_gummel
    mobility = mu_Om
    carrier = rho_mat
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []

  [Op_electrostatic_drift]
    type = PhysicsFVElectrostaticDrift
    variable = w_Op
    potential = potential_from_gummel
    mobility = mu_Op
    carrier = rho_mat
    charge_number = 1
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []

  [O2s_heavy_mass_em_correction]
    type = PhysicsFVHeavyMassElectromigrationCorrection
    variable = w_O2s
    potential = potential_from_gummel
    rho = rho_mat
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_mobilities = 'mu_O2p mu_Om mu_Op'
    ion_charges = '1 -1 1'
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []

  [O2p_heavy_mass_em_correction]
    type = PhysicsFVHeavyMassElectromigrationCorrection
    variable = w_O2p
    potential = potential_from_gummel
    rho = rho_mat
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_mobilities = 'mu_O2p mu_Om mu_Op'
    ion_charges = '1 -1 1'
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []

  [O_heavy_mass_em_correction]
    type = PhysicsFVHeavyMassElectromigrationCorrection
    variable = w_O
    potential = potential_from_gummel
    rho = rho_mat
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_mobilities = 'mu_O2p mu_Om mu_Op'
    ion_charges = '1 -1 1'
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []

  [Om_heavy_mass_em_correction]
    type = PhysicsFVHeavyMassElectromigrationCorrection
    variable = w_Om
    potential = potential_from_gummel
    rho = rho_mat
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_mobilities = 'mu_O2p mu_Om mu_Op'
    ion_charges = '1 -1 1'
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []

  [Op_heavy_mass_em_correction]
    type = PhysicsFVHeavyMassElectromigrationCorrection
    variable = w_Op
    potential = potential_from_gummel
    rho = rho_mat
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_mobilities = 'mu_O2p mu_Om mu_Op'
    ion_charges = '1 -1 1'
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []

  [Os_heavy_mass_em_correction]
    type = PhysicsFVHeavyMassElectromigrationCorrection
    variable = w_Os
    potential = potential_from_gummel
    rho = rho_mat
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_mobilities = 'mu_O2p mu_Om mu_Op'
    ion_charges = '1 -1 1'
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
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
  [O_wall_loss]
    type = FVFunctorNeumannBC
    variable = w_O
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    functor = O_wall_flux_outward
    factor = -1.0
  []
  [O2s_wall_loss]
    type = FVFunctorNeumannBC
    variable = w_O2s
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    functor = O2s_wall_flux_outward
    factor = -1.0
  []
  [Os_wall_loss]
    type = FVFunctorNeumannBC
    variable = w_Os
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    functor = Os_wall_flux_outward
    factor = -1.0
  []
  [O2p_surface_plasma_electrode]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_electrode
    functor = ion_surface_mass_flux_O2p
    factor = -1.0
  []
  [O2p_migration_plasma_electrode]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_electrode
    functor = ion_migration_mass_flux_O2p
    factor = -1.0
  []
  [O2p_surface_plasma_metal]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_metal
    functor = ion_surface_mass_flux_O2p
    factor = -1.0
  []
  [O2p_migration_plasma_metal]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_metal
    functor = ion_migration_mass_flux_O2p
    factor = -1.0
  []
  [O2p_surface_plasma_right]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_right
    functor = ion_surface_mass_flux_O2p
    factor = -1.0
  []
  [O2p_migration_plasma_right]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_right
    functor = ion_migration_mass_flux_O2p
    factor = -1.0
  []
  [O2p_surface_plasma_cover]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_cover
    functor = ion_surface_mass_flux_O2p
    factor = -1.0
  []
  [O2p_migration_plasma_cover]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_cover
    functor = ion_migration_mass_flux_O2p
    factor = -1.0
  []
  [O2p_surface_plasma_wafer]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_wafer
    functor = ion_surface_mass_flux_O2p
    factor = -1.0
  []
  [O2p_migration_plasma_wafer]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_wafer
    functor = ion_migration_mass_flux_O2p
    factor = -1.0
  []
  [O2p_surface_plasma_focus_ring]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_focus_ring
    functor = ion_surface_mass_flux_O2p
    factor = -1.0
  []
  [O2p_migration_plasma_focus_ring]
    type = FVFunctorNeumannBC
    variable = w_O2p
    boundary = plasma_focus_ring
    functor = ion_migration_mass_flux_O2p
    factor = -1.0
  []
  [Om_surface_plasma_electrode]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_electrode
    functor = ion_surface_mass_flux_Om
    factor = -1.0
  []
  [Om_migration_plasma_electrode]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_electrode
    functor = ion_migration_mass_flux_Om
    factor = -1.0
  []
  [Om_surface_plasma_metal]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_metal
    functor = ion_surface_mass_flux_Om
    factor = -1.0
  []
  [Om_migration_plasma_metal]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_metal
    functor = ion_migration_mass_flux_Om
    factor = -1.0
  []
  [Om_surface_plasma_right]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_right
    functor = ion_surface_mass_flux_Om
    factor = -1.0
  []
  [Om_migration_plasma_right]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_right
    functor = ion_migration_mass_flux_Om
    factor = -1.0
  []
  [Om_surface_plasma_cover]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_cover
    functor = ion_surface_mass_flux_Om
    factor = -1.0
  []
  [Om_migration_plasma_cover]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_cover
    functor = ion_migration_mass_flux_Om
    factor = -1.0
  []
  [Om_surface_plasma_wafer]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_wafer
    functor = ion_surface_mass_flux_Om
    factor = -1.0
  []
  [Om_migration_plasma_wafer]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_wafer
    functor = ion_migration_mass_flux_Om
    factor = -1.0
  []
  [Om_surface_plasma_focus_ring]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_focus_ring
    functor = ion_surface_mass_flux_Om
    factor = -1.0
  []
  [Om_migration_plasma_focus_ring]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = plasma_focus_ring
    functor = ion_migration_mass_flux_Om
    factor = -1.0
  []
  [Op_surface_plasma_electrode]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_electrode
    functor = ion_surface_mass_flux_Op
    factor = -1.0
  []
  [Op_migration_plasma_electrode]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_electrode
    functor = ion_migration_mass_flux_Op
    factor = -1.0
  []
  [Op_surface_plasma_metal]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_metal
    functor = ion_surface_mass_flux_Op
    factor = -1.0
  []
  [Op_migration_plasma_metal]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_metal
    functor = ion_migration_mass_flux_Op
    factor = -1.0
  []
  [Op_surface_plasma_right]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_right
    functor = ion_surface_mass_flux_Op
    factor = -1.0
  []
  [Op_migration_plasma_right]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_right
    functor = ion_migration_mass_flux_Op
    factor = -1.0
  []
  [Op_surface_plasma_cover]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_cover
    functor = ion_surface_mass_flux_Op
    factor = -1.0
  []
  [Op_migration_plasma_cover]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_cover
    functor = ion_migration_mass_flux_Op
    factor = -1.0
  []
  [Op_surface_plasma_wafer]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_wafer
    functor = ion_surface_mass_flux_Op
    factor = -1.0
  []
  [Op_migration_plasma_wafer]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_wafer
    functor = ion_migration_mass_flux_Op
    factor = -1.0
  []
  [Op_surface_plasma_focus_ring]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_focus_ring
    functor = ion_surface_mass_flux_Op
    factor = -1.0
  []
  [Op_migration_plasma_focus_ring]
    type = FVFunctorNeumannBC
    variable = w_Op
    boundary = plasma_focus_ring
    functor = ion_migration_mass_flux_Op
    factor = -1.0
  []
  [ion_neutralization_O_return]
    type = FVFunctorNeumannBC
    variable = w_O
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    functor = ion_neutralization_O_return_mass_flux_inward
    factor = 1.0
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

  [Mn_min]
    type = ADElementExtremeFunctorValue
    functor = Mn_mix
    value_type = min
    block = plasma
  []
  [Mn_max]
    type = ADElementExtremeFunctorValue
    functor = Mn_mix
    value_type = max
    block = plasma
  []
  [drho_dt_avg]
    type = ElementAverageFunctorPostprocessor
    functor = drho_dt_model
    block = plasma
  []
  [dMn_dt_avg]
    type = ElementAverageFunctorPostprocessor
    functor = dMn_dt_model
    block = plasma
  []

  [mass_total]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_mat
    block = plasma
  []
  [mass_O2]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O2
    block = plasma
  []
  [mass_O2s]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O2s
    block = plasma
  []
  [mass_O2p]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O2p
    block = plasma
  []
  [mass_O]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O
    block = plasma
  []
  [mass_Om]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_Om
    block = plasma
  []
  [mass_Op]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_Op
    block = plasma
  []
  [mass_Os]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_Os
    block = plasma
  []

  [mu_O2p_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mu_O2p
    block = plasma
  []
  [mu_Om_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mu_Om
    block = plasma
  []
  [mu_Op_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mu_Op
    block = plasma
  []

  [O_wall_rate]
    type = SideFVFluxBCIntegral
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    fvbcs = 'O_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2s_wall_rate]
    type = SideFVFluxBCIntegral
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    fvbcs = 'O2s_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Os_wall_rate]
    type = SideFVFluxBCIntegral
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    fvbcs = 'Os_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_surface_plasma_electrode_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_electrode
    fvbcs = 'O2p_surface_plasma_electrode'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_migration_plasma_electrode_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_electrode
    fvbcs = 'O2p_migration_plasma_electrode'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_surface_plasma_metal_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_metal
    fvbcs = 'O2p_surface_plasma_metal'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_migration_plasma_metal_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_metal
    fvbcs = 'O2p_migration_plasma_metal'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_surface_plasma_right_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_right
    fvbcs = 'O2p_surface_plasma_right'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_migration_plasma_right_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_right
    fvbcs = 'O2p_migration_plasma_right'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_surface_plasma_cover_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_cover
    fvbcs = 'O2p_surface_plasma_cover'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_migration_plasma_cover_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_cover
    fvbcs = 'O2p_migration_plasma_cover'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_surface_plasma_wafer_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_wafer
    fvbcs = 'O2p_surface_plasma_wafer'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_migration_plasma_wafer_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_wafer
    fvbcs = 'O2p_migration_plasma_wafer'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_surface_plasma_focus_ring_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_focus_ring
    fvbcs = 'O2p_surface_plasma_focus_ring'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_migration_plasma_focus_ring_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_focus_ring
    fvbcs = 'O2p_migration_plasma_focus_ring'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_surface_plasma_electrode_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_electrode
    fvbcs = 'Om_surface_plasma_electrode'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_migration_plasma_electrode_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_electrode
    fvbcs = 'Om_migration_plasma_electrode'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_surface_plasma_metal_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_metal
    fvbcs = 'Om_surface_plasma_metal'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_migration_plasma_metal_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_metal
    fvbcs = 'Om_migration_plasma_metal'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_surface_plasma_right_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_right
    fvbcs = 'Om_surface_plasma_right'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_migration_plasma_right_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_right
    fvbcs = 'Om_migration_plasma_right'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_surface_plasma_cover_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_cover
    fvbcs = 'Om_surface_plasma_cover'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_migration_plasma_cover_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_cover
    fvbcs = 'Om_migration_plasma_cover'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_surface_plasma_wafer_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_wafer
    fvbcs = 'Om_surface_plasma_wafer'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_migration_plasma_wafer_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_wafer
    fvbcs = 'Om_migration_plasma_wafer'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_surface_plasma_focus_ring_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_focus_ring
    fvbcs = 'Om_surface_plasma_focus_ring'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_migration_plasma_focus_ring_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_focus_ring
    fvbcs = 'Om_migration_plasma_focus_ring'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_surface_plasma_electrode_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_electrode
    fvbcs = 'Op_surface_plasma_electrode'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_migration_plasma_electrode_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_electrode
    fvbcs = 'Op_migration_plasma_electrode'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_surface_plasma_metal_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_metal
    fvbcs = 'Op_surface_plasma_metal'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_migration_plasma_metal_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_metal
    fvbcs = 'Op_migration_plasma_metal'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_surface_plasma_right_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_right
    fvbcs = 'Op_surface_plasma_right'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_migration_plasma_right_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_right
    fvbcs = 'Op_migration_plasma_right'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_surface_plasma_cover_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_cover
    fvbcs = 'Op_surface_plasma_cover'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_migration_plasma_cover_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_cover
    fvbcs = 'Op_migration_plasma_cover'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_surface_plasma_wafer_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_wafer
    fvbcs = 'Op_surface_plasma_wafer'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_migration_plasma_wafer_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_wafer
    fvbcs = 'Op_migration_plasma_wafer'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_surface_plasma_focus_ring_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_focus_ring
    fvbcs = 'Op_surface_plasma_focus_ring'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_migration_plasma_focus_ring_rate]
    type = SideFVFluxBCIntegral
    boundary = plasma_focus_ring
    fvbcs = 'Op_migration_plasma_focus_ring'
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]


[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]

[AuxVariables]
  [T_g_snapshot]
    type = MooseVariableFVReal
    initial_condition = 300
  []
  [electron_density_from_gummel]
    type = MooseVariableFVReal
    initial_condition = 3218833278166041
  []
  [mean_energy_from_gummel]
    type = MooseVariableFVReal
    initial_condition = 5.7327599999999999
  []
  [potential_from_gummel]
    type = MooseVariableFVReal
    initial_condition = 0
  []
[]

[MultiApps]
  [gummel_driver]
    type = TransientMultiApp
    input_files = 'gummel_driver.i'
    execute_on = TIMESTEP_BEGIN
    no_restore = true
    sub_cycling = true
  []
[]

[Transfers]
  [heavy_state_to_gummel]
    type = MultiAppCopyTransfer
    to_multi_app = gummel_driver
    source_variable = 'p T_g_snapshot w_O2p w_Om w_Op'
    variable = 'p_gas_h T_g_h w_O2p_h w_Om_h w_Op_h'
  []
  [gummel_state_to_heavy]
    type = MultiAppCopyTransfer
    from_multi_app = gummel_driver
    source_variable = 'electron_density_out mean_energy_out potential_from_poisson'
    variable = 'electron_density_from_gummel mean_energy_from_gummel potential_from_gummel'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 2.2660316009047157e-10
  end_time = 2.2660316009047157e-10
  num_steps = 1
  nl_rel_tol = 1.0e-9
  nl_abs_tol = 1.0e-11
  nl_max_its = 80
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]
