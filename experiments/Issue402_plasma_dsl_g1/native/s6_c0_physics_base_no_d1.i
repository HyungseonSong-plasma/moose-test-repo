# Issue #3 practical baseline dielectric pilot
# Derived from the accepted Issue #331 15 us Stage-B4 baseline evidence.
# Retains the first 100 x 1 ns baseline timesteps for a clean A/B discriminator.
# Cover relative permittivity eps_r=3.6 follows the original QVT geometry/material provenance.
# SEE is disabled in this first practical pilot; cover bulk-conductivity leakage is not yet modeled.

[Mesh]
  coord_type = RZ
  rz_coord_axis = Y
  [main]
    type = FileMeshGenerator
    file = 'baseline_plasma_plus_unstructured_cover_plus_wafer.msh'
  []
  [plasma_cover_owner]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = cover
    new_boundary = plasma_cover_owner
    input = main
  []
  [plasma_wafer_owner]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = wafer
    new_boundary = plasma_wafer_owner
    input = plasma_cover_owner
  []
  [plasma_focus_ring_owner]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = focus_ring
    new_boundary = plasma_focus_ring_owner
    input = plasma_wafer_owner
  []
  [cover_surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = plasma_focus_ring_owner
    sidesets = plasma_cover_owner
    new_block_id = 30
    new_block_name = cover_surface
  []
  [wafer_surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = cover_surface_block
    sidesets = plasma_wafer_owner
    new_block_id = 31
    new_block_name = wafer_surface
  []
  [focus_ring_surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = wafer_surface_block
    sidesets = plasma_focus_ring_owner
    new_block_id = 32
    new_block_name = focus_ring_surface
  []
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
    initial_condition = 0.0
    block = plasma
  []
  [v]
    type = INSFVVelocityVariable
    initial_condition = 0.0
    block = plasma
  []
  [p]
    type = INSFVPressureVariable
    initial_condition = 1.333223684
    block = plasma
  []
  [w_O2s]
    type = INSFVScalarFieldVariable
    initial_condition = 1.000010000100001e-05
    block = plasma
  []
  [w_O]
    type = INSFVScalarFieldVariable
    initial_condition = 5.0000500005000049e-06
    block = plasma
  []
  [w_Os]
    type = INSFVScalarFieldVariable
    initial_condition = 5.0000500005000049e-06
    block = plasma
  []
  [log_ne]
    family = LAGRANGE
    order = FIRST
    initial_condition = -20.216123548032986
    block = plasma
  []
  [log_ni]
    type = MooseVariableFVReal
    initial_condition = -20.216123548032986
    block = plasma
  []
  [log_nm]
    type = MooseVariableFVReal
    initial_condition = -27.123878827015126
    block = plasma
  []
  [log_nop]
    type = MooseVariableFVReal
    initial_condition = -27.123878827015126
    block = plasma
  []
  [log_energy]
    family = LAGRANGE
    order = FIRST
    initial_condition = -18.829829186913098
    block = plasma
  []
  [potential]
    family = LAGRANGE
    order = FIRST
    initial_condition = 0.0
    block = 'plasma cover wafer focus_ring vacuum coil1 coil2 coil3'
  []
  [sigma_s]
    family = MONOMIAL
    order = CONSTANT
    initial_condition = 0.0
    block = cover_surface
  []
  [sigma_wafer]
    family = MONOMIAL
    order = CONSTANT
    initial_condition = 0.0
    block = wafer_surface
  []
  [sigma_focus_ring]
    family = MONOMIAL
    order = CONSTANT
    initial_condition = 0.0
    block = focus_ring_surface
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'p_fixed T_g_fixed ion_mobility ion_diffusion negative_ion_mobility negative_ion_diffusion atomic_positive_ion_mobility atomic_positive_ion_diffusion carrier_one'
    prop_values = '1.333223684 300 10 0.25851999786435537 10 0.25851999786435537 10 0.25851999786435537 1.0'
    block = plasma
  []
  [electron_molar_density]
    type = ADParsedFunctorMaterial
    property_name = electron_molar_density
    functor_names = 'log_ne'
    functor_symbols = 'u'
    expression = 'exp(u)'
    block = plasma
  []
  [ion_molar_density]
    type = ADParsedFunctorMaterial
    property_name = ion_molar_density
    functor_names = 'log_ni'
    functor_symbols = 'u'
    expression = 'exp(u)'
    block = plasma
  []
  [electron_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'electron_molar_density'
    functor_symbols = 'ce'
    expression = '6.02214076e23*ce'
    block = plasma
  []
  [ion_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_i_physical
    functor_names = 'ion_molar_density'
    functor_symbols = 'ci'
    expression = '6.02214076e23*ci'
    block = plasma
  []
  [negative_ion_molar_density]
    type = ADParsedFunctorMaterial
    property_name = negative_ion_molar_density
    functor_names = 'log_nm'
    functor_symbols = 'u'
    expression = 'exp(u)'
    block = plasma
  []
  [negative_ion_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_m_physical
    functor_names = 'negative_ion_molar_density'
    functor_symbols = 'cm'
    expression = '6.02214076e23*cm'
    block = plasma
  []
  [atomic_positive_ion_molar_density]
    type = ADParsedFunctorMaterial
    property_name = atomic_positive_ion_molar_density
    functor_names = 'log_nop'
    functor_symbols = 'u'
    expression = 'exp(u)'
    block = plasma
  []
  [atomic_positive_ion_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_op_physical
    functor_names = 'atomic_positive_ion_molar_density'
    functor_symbols = 'cop'
    expression = '6.02214076e23*cop'
    block = plasma
  []
  [electron_molar_energy_density]
    type = ADParsedFunctorMaterial
    property_name = electron_molar_energy_density
    functor_names = 'log_energy'
    functor_symbols = 'ue'
    expression = 'exp(ue)'
    block = plasma
  []
  [electron_physical_energy_density]
    type = ADParsedFunctorMaterial
    property_name = electron_energy_density_eV_m3
    functor_names = 'electron_molar_energy_density'
    functor_symbols = 'we'
    expression = '6.02214076e23*we'
    block = plasma
  []
  [mean_energy]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = log_energy
    electron_density = log_ne
    state_form = log_molar_eV
    block = plasma
  []
  [electron_transport]
    type = PhysicsElectronTransportLookupMaterial
    property_table_file = '../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'
    mean_energy = mean_en_solved
    pressure = p
    gas_temperature = T_g_fixed
    bounds_policy = clamp
    block = plasma
  []
  [charge_number_density]
    type = ADParsedFunctorMaterial
    property_name = charge_number_density
    functor_names = 'n_i_physical n_op_physical n_e_physical n_m_physical'
    functor_symbols = 'ni nop ne nm'
    expression = 'ni+nop-ne-nm'
    block = plasma
  []
  [charge_density]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.602176634e-19*nq'
    block = plasma
  []
  [poisson_source]
    type = ADParsedFunctorMaterial
    property_name = poisson_source
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.8095128179727827e-08*nq'
    block = plasma
  []
  [ion_wall_flux]
    type = PhysicsIonWallTotalFluxMaterial
    use_element_gradient_for_potential = true
    ion_number_density = n_i_physical
    potential = potential
    mobility = ion_mobility
    gas_temperature = T_g_fixed
    charge_number = 1
    molar_mass = 0.032
    sticking = 1.0
    ion_temperature_eV = 0.0
    migration_gate_smoothing_width = 1.0e-3
    block = plasma
  []
  [negative_ion_wall_flux]
    type = PhysicsIonWallTotalFluxMaterial
    output_prefix = negative_
    use_element_gradient_for_potential = true
    ion_number_density = n_m_physical
    potential = potential
    mobility = negative_ion_mobility
    gas_temperature = T_g_fixed
    charge_number = -1
    molar_mass = 0.016
    sticking = 1.0
    ion_temperature_eV = 0.0
    migration_gate_smoothing_width = 1.0e-3
    block = plasma
  []
  [atomic_positive_ion_wall_flux]
    type = PhysicsIonWallTotalFluxMaterial
    output_prefix = atomic_positive_
    use_element_gradient_for_potential = true
    ion_number_density = n_op_physical
    potential = potential
    mobility = atomic_positive_ion_mobility
    gas_temperature = T_g_fixed
    charge_number = 1
    molar_mass = 0.016
    sticking = 1.0
    ion_temperature_eV = 0.0
    migration_gate_smoothing_width = 1.0e-3
    block = plasma
  []
  [electron_wall_flux]
    type = PhysicsElectronAdjacentSheathWallFluxMaterial
    electron_density = n_e_physical
    mean_energy = mean_en_solved
    sticking = 1.0
    block = plasma
    potential = potential
    use_element_gradient_for_potential = true
  []
  [cover_surface_current]
    type = ADParsedFunctorMaterial
    property_name = cover_net_surface_current_density
    functor_names = 'ion_wall_number_flux atomic_positive_ion_wall_number_flux negative_ion_wall_number_flux electron_wall_number_flux'
    functor_symbols = 'gi gop gm ge'
    expression = '1.602176634e-19*(gi+gop-gm-ge)'
    block = plasma
  []
  [wafer_surface_current]
    type = ADParsedFunctorMaterial
    property_name = wafer_net_surface_current_density
    functor_names = 'ion_wall_number_flux atomic_positive_ion_wall_number_flux negative_ion_wall_number_flux electron_wall_number_flux'
    functor_symbols = 'gi gop gm ge'
    expression = '1.602176634e-19*(gi+gop-gm-ge)'
    block = plasma
  []
  [focus_ring_surface_current]
    type = ADParsedFunctorMaterial
    property_name = focus_ring_net_surface_current_density
    functor_names = 'ion_wall_number_flux atomic_positive_ion_wall_number_flux negative_ion_wall_number_flux electron_wall_number_flux'
    functor_symbols = 'gi gop gm ge'
    expression = '1.602176634e-19*(gi+gop-gm-ge)'
    block = plasma
  []

  [neutral_flow_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mu_flow'
    prop_values = '2.0000000000000002e-05'
    block = plasma
  []

  [neutral_state_dot_aliases]
    type = ADGenericFunctorMaterial
    prop_names = 'p_state wO_state wOs_state'
    prop_values = 'p w_O w_Os'
    define_dot_functors = true
    block = plasma
  []

  [neutral_O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O2s w_O w_Os'
    functor_symbols = 's o a'
    expression = '1.0-s-o-a'
    block = plasma
  []

  [neutral_mean_molar_mass]
    type = ADParsedFunctorMaterial
    property_name = Mn_neutral
    functor_names = 'w_O2_constraint w_O2s w_O w_Os'
    functor_symbols = 'm0 m1 m2 m3'
    expression = '1.0/(m0/0.032+m1/0.032+m2/0.016+m3/0.016)'
    block = plasma
  []

  [neutral_density]
    type = ADParsedFunctorMaterial
    property_name = rho_neutral
    functor_names = 'p Mn_neutral T_g_fixed'
    functor_symbols = 'prs mol tmp'
    expression = 'prs*mol/(8.31446*tmp)'
    block = plasma
  []

  # A = w_O + w_O*. Molecular redistribution O2 <-> O2* leaves Mn unchanged.
  # Mn = 0.032/(1+A), hence dMn/dt = -31.25*Mn^2*dA/dt.
  [neutral_mean_molar_mass_dot]
    type = ADParsedFunctorMaterial
    property_name = dMn_neutral_dt
    functor_names = 'Mn_neutral dwO_state_dt dwOs_state_dt'
    functor_symbols = 'mn dwo dwos'
    expression = '-31.25*mn*mn*(dwo+dwos)'
    block = plasma
  []

  # Isothermal Stage-B flow: rho = p*Mn/(R*Tg).
  [neutral_density_dot]
    type = ADParsedFunctorMaterial
    property_name = drho_neutral_dt
    functor_names = 'p Mn_neutral dp_state_dt dMn_neutral_dt T_g_fixed'
    functor_symbols = 'prs mn dp dmn tmp'
    expression = '(mn*dp+prs*dmn)/(8.31446*tmp)'
    block = plasma
  []

  [neutral_sum_w]
    type = ADParsedFunctorMaterial
    property_name = neutral_sum_w_functor
    functor_names = 'w_O2_constraint w_O2s w_O w_Os'
    functor_symbols = 'q0 q1 q2 q3'
    expression = 'q0+q1+q2+q3'
    block = plasma
  []

  [rho_w_O2]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O2
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w'
    block = plasma
  []
  [rho_w_O2s]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O2s
    functor_names = 'rho_neutral w_O2s'
    functor_symbols = 'rho w'
    expression = 'rho*w'
    block = plasma
  []
  [rho_w_O]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O
    functor_names = 'rho_neutral w_O'
    functor_symbols = 'rho w'
    expression = 'rho*w'
    block = plasma
  []
  [rho_w_Os]
    type = ADParsedFunctorMaterial
    property_name = rho_w_Os
    functor_names = 'rho_neutral w_Os'
    functor_symbols = 'rho w'
    expression = 'rho*w'
    block = plasma
  []

  [neutral_transport]
    type = PhysicsThermalDiffusionMaterial
    temperature = T_g_fixed
    pressure = p
    transport_data_file = '../Issue21_qvt_six_species_bulk_advection/transport_data.txt'
    species = 'O2 O2s O Os'
    mass_fractions = 'w_O2_constraint w_O2s w_O w_Os'
    D_mix_names = 'D_mix_O2 D_mix_O2s D_mix_O D_mix_Os'
    D_T_names = 'D_T_O2 D_T_O2s D_T_O D_T_Os'
    kT_names = 'kT_O2 kT_O2s kT_O kT_Os'
    block = plasma
  []



[]

[Materials]
  [eps_plasma]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '1.0'
    block = plasma
  []
  [eps_cover]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '3.6'
    block = cover
  []
  [eps_wafer]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '12.5'
    block = wafer
  []
  [eps_focus_ring]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '8.0'
    block = focus_ring
  []
  [eps_vacuum]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '1.0'
    block = 'vacuum coil1 coil2 coil3'
  []
  [cover_surface_anchor]
    type = ADGenericConstantMaterial
    prop_names = 'cover_surface_anchor'
    prop_values = '0.0'
    block = cover_surface
  []
  [wafer_surface_anchor]
    type = ADGenericConstantMaterial
    prop_names = 'wafer_surface_anchor'
    prop_values = '0.0'
    block = wafer_surface
  []
  [focus_ring_surface_anchor]
    type = ADGenericConstantMaterial
    prop_names = 'focus_ring_surface_anchor'
    prop_values = '0.0'
    block = focus_ring_surface
  []
[]

[Kernels]
  [ne_time]
    type = PhysicsFEMLogMolarTimeDerivative
    variable = log_ne
    block = plasma
  []
  [energy_time]
    type = PhysicsFEMLogMolarTimeDerivative
    variable = log_energy
    block = plasma
  []
  [energy_transport]
    type = PhysicsFEMLogMolarDriftDiffusion
    variable = log_energy
    potential = potential
    mobility = electron_energy_mobility
    diffusion = electron_energy_diffusion
    charge_number = -1
    block = plasma
  []
  [energy_joule]
    type = PhysicsFEMLogMolarElectronJouleHeating
    variable = log_energy
    electron_log_density = log_ne
    potential = potential
    mobility = electron_mobility
    diffusion = electron_diffusion
    block = plasma
  []
  [phi_diffusion]
    type = ADMatDiffusion
    variable = potential
    diffusivity = relative_permittivity
    block = 'plasma cover wafer focus_ring vacuum coil1 coil2 coil3'
  []
  [phi_source]
    type = FunctorKernel
    variable = potential
    functor = poisson_source
    functor_on_rhs = true
    block = plasma
  []
  [sigma_time]
    type = ADTimeDerivative
    variable = sigma_s
    block = cover_surface
  []
  [sigma_surface_current]
    type = PhysicsLowerDSurfaceCurrent
    variable = sigma_s
    surface_current_density = cover_net_surface_current_density
    block = cover_surface
  []
  [sigma_wafer_time]
    type = ADTimeDerivative
    variable = sigma_wafer
    block = wafer_surface
  []
  [sigma_wafer_surface_current]
    type = PhysicsLowerDSurfaceCurrent
    variable = sigma_wafer
    surface_current_density = wafer_net_surface_current_density
    block = wafer_surface
  []
  [sigma_focus_ring_time]
    type = ADTimeDerivative
    variable = sigma_focus_ring
    block = focus_ring_surface
  []
  [sigma_focus_ring_surface_current]
    type = PhysicsLowerDSurfaceCurrent
    variable = sigma_focus_ring
    surface_current_density = focus_ring_net_surface_current_density
    block = focus_ring_surface
  []
[]


[FVKernels]
  [ni_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ni
    block = plasma
  []
  [ni_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ni
    coeff = ion_diffusion
    block = plasma
  []
  [ni_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_ni
    potential = potential
    mobility = ion_mobility
    carrier = carrier_one
    charge_number = 1
    advected_interp_method = upwind
    use_element_gradient_for_potential = true
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []
  [nm_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_nm
    block = plasma
  []
  [nm_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_nm
    coeff = negative_ion_diffusion
    block = plasma
  []
  [nm_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_nm
    potential = potential
    mobility = negative_ion_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    use_element_gradient_for_potential = true
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []
  [nop_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_nop
    block = plasma
  []
  [nop_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_nop
    coeff = atomic_positive_ion_diffusion
    block = plasma
  []
  [nop_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_nop
    potential = potential
    mobility = atomic_positive_ion_mobility
    carrier = carrier_one
    charge_number = 1
    advected_interp_method = upwind
    use_element_gradient_for_potential = true
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []
  [neutral_mass_time]
    type = WCNSFVMassTimeDerivative
    variable = p
    drho_dt = drho_neutral_dt
    block = plasma
  []
  [neutral_mass_advection]
    type = INSFVMassAdvection
    variable = p
    rho = rho_neutral
    block = plasma
  []

  [u_advection]
    type = INSFVMomentumAdvection
    variable = u
    rho = rho_neutral
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
    rho = rho_neutral
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
    rho = rho_neutral
    block = plasma
  []
  [O2s_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_O2s
    rho = rho_neutral
    block = plasma
  []
  [O2s_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_O2s
    rho = rho_neutral
    diffusivity = D_mix_O2s
    mean_molar_mass = Mn_neutral
    include_molar_mass_gradient = true
    block = plasma
  []

  [O_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_O
    rho = rho_neutral
    block = plasma
  []
  [O_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_O
    rho = rho_neutral
    block = plasma
  []
  [O_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_O
    rho = rho_neutral
    diffusivity = D_mix_O
    mean_molar_mass = Mn_neutral
    include_molar_mass_gradient = true
    block = plasma
  []

  [Os_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_Os
    rho = rho_neutral
    block = plasma
  []
  [Os_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_Os
    rho = rho_neutral
    block = plasma
  []
  [Os_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_Os
    rho = rho_neutral
    diffusivity = D_mix_Os
    mean_molar_mass = Mn_neutral
    include_molar_mass_gradient = true
    block = plasma
  []

[]

[BCs]
  [electron_sheath]
    type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC
    variable = log_ne
    wall_number_flux = electron_wall_number_flux
    boundary = 'plasma_electrode plasma_metal plasma_right'
  []
  [electron_cover_dielectric]
    type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC
    variable = log_ne
    wall_number_flux = electron_wall_number_flux
    boundary = 'plasma_cover'
  []
  [electron_wafer_dielectric]
    type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC
    variable = log_ne
    wall_number_flux = electron_wall_number_flux
    boundary = 'plasma_wafer'
  []
  [electron_focus_ring_dielectric]
    type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC
    variable = log_ne
    wall_number_flux = electron_wall_number_flux
    boundary = 'plasma_focus_ring'
  []
  [electron_energy_sheath]
    type = PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC
    variable = log_energy
    wall_number_flux = electron_wall_number_flux
    mean_energy = mean_en_solved
    boundary = 'plasma_electrode plasma_metal plasma_right'
  []
  [electron_energy_cover]
    type = PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC
    variable = log_energy
    wall_number_flux = electron_wall_number_flux
    mean_energy = mean_en_solved
    boundary = 'plasma_cover'
  []
  [electron_energy_wafer]
    type = PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC
    variable = log_energy
    wall_number_flux = electron_wall_number_flux
    mean_energy = mean_en_solved
    boundary = 'plasma_wafer'
  []
  [electron_energy_focus_ring]
    type = PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC
    variable = log_energy
    wall_number_flux = electron_wall_number_flux
    mean_energy = mean_en_solved
    boundary = 'plasma_focus_ring'
  []
  [grounded_potential]
    type = DirichletBC
    variable = potential
    value = 0.0
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right cover_outer_right wafer_electrode focus_ring_ground vacuum_outer_ground cover_coil_ground vacuum_coil_ground'
  []
  [cover_surface_charge_poisson]
    type = PhysicsADSurfaceChargePoissonBC
    variable = potential
    boundary = plasma_cover
    surface_charge = sigma_s
  []
  [wafer_surface_charge_poisson]
    type = PhysicsADSurfaceChargePoissonBC
    variable = potential
    boundary = plasma_wafer
    surface_charge = sigma_wafer
  []
  [focus_ring_surface_charge_poisson]
    type = PhysicsADSurfaceChargePoissonBC
    variable = potential
    boundary = plasma_focus_ring
    surface_charge = sigma_focus_ring
  []
[]


[FVBCs]
  [ion_wall]
    type = FVFunctorNeumannBC
    variable = log_ni
    functor = ion_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right'
  []
  [negative_ion_wall]
    type = FVFunctorNeumannBC
    variable = log_nm
    functor = negative_ion_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right'
  []
  [atomic_positive_ion_wall]
    type = FVFunctorNeumannBC
    variable = log_nop
    functor = atomic_positive_ion_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right'
  []
  [ion_cover_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_ni
    signed_number_flux = ion_wall_number_flux
    boundary = plasma_cover
  []
  [negative_ion_cover_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nm
    signed_number_flux = negative_ion_wall_number_flux
    boundary = plasma_cover
  []
  [atomic_positive_ion_cover_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nop
    signed_number_flux = atomic_positive_ion_wall_number_flux
    boundary = plasma_cover
  []
  [ion_wafer_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_ni
    signed_number_flux = ion_wall_number_flux
    boundary = plasma_wafer
  []
  [negative_ion_wafer_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nm
    signed_number_flux = negative_ion_wall_number_flux
    boundary = plasma_wafer
  []
  [atomic_positive_ion_wafer_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nop
    signed_number_flux = atomic_positive_ion_wall_number_flux
    boundary = plasma_wafer
  []
  [ion_focus_ring_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_ni
    signed_number_flux = ion_wall_number_flux
    boundary = plasma_focus_ring
  []
  [negative_ion_focus_ring_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nm
    signed_number_flux = negative_ion_wall_number_flux
    boundary = plasma_focus_ring
  []
  [atomic_positive_ion_focus_ring_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nop
    signed_number_flux = atomic_positive_ion_wall_number_flux
    boundary = plasma_focus_ring
  []
  [neutral_inlet_mass]
    type = WCNSFVMassFluxBC
    variable = p
    boundary = inlet
    mdot_pp = neutral_inlet_mdot
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []
  [neutral_inlet_u]
    type = WCNSFVMomentumFluxBC
    variable = u
    boundary = inlet
    mdot_pp = neutral_inlet_mdot
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    momentum_component = x
    direction = '-1 0 0'
  []
  [neutral_inlet_v]
    type = WCNSFVMomentumFluxBC
    variable = v
    boundary = inlet
    mdot_pp = neutral_inlet_mdot
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    momentum_component = y
    direction = '-1 0 0'
  []

  [neutral_inlet_O2s]
    type = WCNSFVScalarFluxBC
    variable = w_O2s
    boundary = inlet
    passive_scalar = w_O2s
    scalar_flux_pp = neutral_inlet_mdot_O2s
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []
  [neutral_inlet_O]
    type = WCNSFVScalarFluxBC
    variable = w_O
    boundary = inlet
    passive_scalar = w_O
    scalar_flux_pp = neutral_inlet_mdot_O
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []
  [neutral_inlet_Os]
    type = WCNSFVScalarFluxBC
    variable = w_Os
    boundary = inlet
    passive_scalar = w_Os
    scalar_flux_pp = neutral_inlet_mdot_Os
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []

  [neutral_wall_u]
    type = INSFVNoSlipWallBC
    variable = u
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    function = 0
  []
  [neutral_wall_v]
    type = INSFVNoSlipWallBC
    variable = v
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    function = 0
  []
  [neutral_outlet_p]
    type = INSFVOutletPressureBC
    variable = p
    boundary = outlet
    function = 1.333223684
  []




[]

[Postprocessors]
  [ne_min]
    type = ADElementExtremeFunctorValue
    functor = n_e_physical
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ne_max]
    type = ADElementExtremeFunctorValue
    functor = n_e_physical
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ni_min]
    type = ADElementExtremeFunctorValue
    functor = n_i_physical
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ni_max]
    type = ADElementExtremeFunctorValue
    functor = n_i_physical
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_min]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_max]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_min]
    type = ADElementExtremeFunctorValue
    functor = potential
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_max]
    type = ADElementExtremeFunctorValue
    functor = potential
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density_C_m3
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [nm_min]
    type = ADElementExtremeFunctorValue
    functor = n_m_physical
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [nm_max]
    type = ADElementExtremeFunctorValue
    functor = n_m_physical
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_number_min]
    type = ADElementExtremeFunctorValue
    functor = charge_number_density
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_number_max]
    type = ADElementExtremeFunctorValue
    functor = charge_number_density
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [nop_min]
    type = ADElementExtremeFunctorValue
    functor = n_op_physical
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [nop_max]
    type = ADElementExtremeFunctorValue
    functor = n_op_physical
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_inlet_area]
    type = AreaPostprocessor
    boundary = inlet
    execute_on = INITIAL
  []
  [neutral_inlet_mdot]
    type = Receiver
    default = 4.758967769568476e-06
  []
  [neutral_inlet_mdot_O2]
    type = Receiver
    default = 4.7588725892612807e-06
  []
  [neutral_inlet_mdot_O2s]
    type = Receiver
    default = 4.759015359722073e-11
  []
  [neutral_inlet_mdot_O]
    type = Receiver
    default = 2.3795076798610365e-11
  []
  [neutral_inlet_mdot_Os]
    type = Receiver
    default = 2.3795076798610365e-11
  []

  [neutral_outlet_mass]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_neutral
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_outlet_mdot_O2]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_O2
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_outlet_mdot_O2s]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_O2s
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_outlet_mdot_O]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_O
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_outlet_mdot_Os]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_Os
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [neutral_sum_w_min]
    type = ADElementExtremeFunctorValue
    functor = neutral_sum_w_functor
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_sum_w_max]
    type = ADElementExtremeFunctorValue
    functor = neutral_sum_w_functor
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [w_O2_min]
    type = ADElementExtremeFunctorValue
    functor = w_O2_constraint
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2_max]
    type = ADElementExtremeFunctorValue
    functor = w_O2_constraint
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2s_min]
    type = ADElementExtremeFunctorValue
    functor = w_O2s
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2s_max]
    type = ADElementExtremeFunctorValue
    functor = w_O2s
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O_min]
    type = ADElementExtremeFunctorValue
    functor = w_O
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O_max]
    type = ADElementExtremeFunctorValue
    functor = w_O
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_Os_min]
    type = ADElementExtremeFunctorValue
    functor = w_Os
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_Os_max]
    type = ADElementExtremeFunctorValue
    functor = w_Os
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [neutral_Mn_min]
    type = ADElementExtremeFunctorValue
    functor = Mn_neutral
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_Mn_max]
    type = ADElementExtremeFunctorValue
    functor = Mn_neutral
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_rho_min]
    type = ADElementExtremeFunctorValue
    functor = rho_neutral
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_rho_max]
    type = ADElementExtremeFunctorValue
    functor = rho_neutral
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_p_min]
    type = ADElementExtremeFunctorValue
    functor = p
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_p_max]
    type = ADElementExtremeFunctorValue
    functor = p
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_u_min]
    type = ADElementExtremeFunctorValue
    functor = u
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_u_max]
    type = ADElementExtremeFunctorValue
    functor = u
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_v_min]
    type = ADElementExtremeFunctorValue
    functor = v
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_v_max]
    type = ADElementExtremeFunctorValue
    functor = v
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [cover_net_surface_current]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_cover
    functor = cover_net_surface_current_density
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [cover_electron_primary_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_cover
    functor = electron_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [cover_O2p_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_cover
    functor = ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [cover_Om_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_cover
    functor = negative_ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [cover_Op_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_cover
    functor = atomic_positive_ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [cover_surface_charge_total]
    type = ElementIntegralVariablePostprocessor
    variable = sigma_s
    block = cover_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [cover_sigma_average]
    type = ElementAverageValue
    variable = sigma_s
    block = cover_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [cover_sigma_min]
    type = ElementExtremeValue
    variable = sigma_s
    value_type = min
    block = cover_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [cover_sigma_max]
    type = ElementExtremeValue
    variable = sigma_s
    value_type = max
    block = cover_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [cover_interface_potential]
    type = SideAverageValue
    variable = potential
    boundary = plasma_cover
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_net_surface_current]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_wafer
    functor = wafer_net_surface_current_density
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [wafer_electron_primary_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_wafer
    functor = electron_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [wafer_O2p_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_wafer
    functor = ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [wafer_Om_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_wafer
    functor = negative_ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [wafer_Op_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_wafer
    functor = atomic_positive_ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [wafer_surface_charge_total]
    type = ElementIntegralVariablePostprocessor
    variable = sigma_wafer
    block = wafer_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_sigma_average]
    type = ElementAverageValue
    variable = sigma_wafer
    block = wafer_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_sigma_min]
    type = ElementExtremeValue
    variable = sigma_wafer
    value_type = min
    block = wafer_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_sigma_max]
    type = ElementExtremeValue
    variable = sigma_wafer
    value_type = max
    block = wafer_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_interface_potential]
    type = SideAverageValue
    variable = potential
    boundary = plasma_wafer
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_ground_potential]
    type = SideAverageValue
    variable = potential
    boundary = wafer_electrode
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_net_surface_current]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_focus_ring
    functor = focus_ring_net_surface_current_density
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [focus_ring_electron_primary_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_focus_ring
    functor = electron_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [focus_ring_O2p_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_focus_ring
    functor = ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [focus_ring_Om_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_focus_ring
    functor = negative_ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [focus_ring_Op_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_focus_ring
    functor = atomic_positive_ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [focus_ring_surface_charge_total]
    type = ElementIntegralVariablePostprocessor
    variable = sigma_focus_ring
    block = focus_ring_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_sigma_average]
    type = ElementAverageValue
    variable = sigma_focus_ring
    block = focus_ring_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_sigma_min]
    type = ElementExtremeValue
    variable = sigma_focus_ring
    value_type = min
    block = focus_ring_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_sigma_max]
    type = ElementExtremeValue
    variable = sigma_focus_ring
    value_type = max
    block = focus_ring_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_interface_potential]
    type = SideAverageValue
    variable = potential
    boundary = plasma_focus_ring
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_ground_potential]
    type = SideAverageValue
    variable = potential
    boundary = focus_ring_ground
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [vacuum_outer_ground_potential]
    type = SideAverageValue
    variable = potential
    boundary = vacuum_outer_ground
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [cover_coil_ground_potential]
    type = SideAverageValue
    variable = potential
    boundary = cover_coil_ground
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [vacuum_coil_ground_potential]
    type = SideAverageValue
    variable = potential
    boundary = vacuum_coil_ground
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [neutral_mass_total]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_neutral
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_mass_O2]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_mass_O2s]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O2s
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_mass_O]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_mass_Os]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_Os
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [stageb4_O2p_wall_mass_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    functor = ion_wall_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [stageb4_Om_wall_mass_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    functor = negative_ion_wall_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [stageb4_Op_wall_mass_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    functor = atomic_positive_ion_wall_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []

[]
[AuxVariables]
[]
[AuxKernels]
[]
[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  end_time = 1e-4
  [TimeStepper]
    type = TimeSequenceStepper
    time_sequence = '0 1.0000000000000001e-09 2.0000000000000001e-09 3.0000000000000004e-09 4.0000000000000002e-09 5.0000000000000001e-09 6.0000000000000008e-09 7.0000000000000006e-09 8.0000000000000005e-09 9.0000000000000012e-09 1e-08 1.1000000000000001e-08 1.2000000000000002e-08 1.3000000000000001e-08 1.4000000000000001e-08 1.5000000000000002e-08 1.6000000000000001e-08 1.7e-08 1.8000000000000002e-08 1.9000000000000001e-08 2e-08 2.1000000000000003e-08 2.2000000000000002e-08 2.3000000000000001e-08 2.4000000000000003e-08 2.5000000000000002e-08 2.6000000000000001e-08 2.7e-08 2.8000000000000003e-08 2.9000000000000002e-08 3.0000000000000004e-08 3.1e-08 3.2000000000000002e-08 3.3000000000000004e-08 3.4e-08 3.5000000000000002e-08 3.6000000000000005e-08 3.7e-08 3.8000000000000003e-08 3.9000000000000005e-08 4.0000000000000001e-08 4.1000000000000003e-08 4.2000000000000006e-08 4.3000000000000001e-08 4.4000000000000004e-08 4.5000000000000006e-08 4.6000000000000002e-08 4.7000000000000004e-08 4.8000000000000006e-08 4.9000000000000002e-08 5.0000000000000004e-08 5.1e-08 5.2000000000000002e-08 5.3000000000000005e-08 5.4e-08 5.5000000000000003e-08 5.6000000000000005e-08 5.7000000000000001e-08 5.8000000000000003e-08 5.9000000000000006e-08 6.0000000000000008e-08 6.1000000000000004e-08 6.1999999999999999e-08 6.3000000000000008e-08 6.4000000000000004e-08 6.5e-08 6.6000000000000009e-08 6.7000000000000004e-08 6.8e-08 6.9000000000000009e-08 7.0000000000000005e-08 7.1e-08 7.2000000000000009e-08 7.3000000000000005e-08 7.4000000000000001e-08 7.500000000000001e-08 7.6000000000000006e-08 7.7000000000000001e-08 7.800000000000001e-08 7.9000000000000006e-08 8.0000000000000002e-08 8.1000000000000011e-08 8.2000000000000006e-08 8.3000000000000002e-08 8.4000000000000011e-08 8.5000000000000007e-08 8.6000000000000002e-08 8.7000000000000011e-08 8.8000000000000007e-08 8.9000000000000003e-08 9.0000000000000012e-08 9.1000000000000008e-08 9.2000000000000003e-08 9.3000000000000012e-08 9.4000000000000008e-08 9.5000000000000004e-08 9.6000000000000013e-08 9.7000000000000008e-08 9.8000000000000004e-08 9.9e-08 1.0000000000000001e-07 1.1000000000000001e-07 1.2000000000000002e-07 1.3e-07 1.4000000000000001e-07 1.5000000000000002e-07 1.6e-07 1.7000000000000001e-07 1.8000000000000002e-07 1.9000000000000001e-07 2.0000000000000002e-07 2.1e-07 2.2000000000000001e-07 2.3000000000000002e-07 2.4000000000000003e-07 2.5000000000000004e-07 2.6e-07 2.7000000000000001e-07 2.8000000000000002e-07 2.9000000000000003e-07 3.0000000000000004e-07 3.1e-07 3.2000000000000001e-07 3.3000000000000002e-07 3.4000000000000003e-07 3.5000000000000004e-07 3.6000000000000005e-07 3.7e-07 3.8000000000000001e-07 3.9000000000000002e-07 4.0000000000000003e-07 4.1000000000000004e-07 4.2e-07 4.3000000000000001e-07 4.4000000000000002e-07 4.5000000000000003e-07 4.6000000000000004e-07 4.7000000000000005e-07 4.8000000000000006e-07 4.9000000000000007e-07 5.0000000000000008e-07 5.0999999999999999e-07 5.2e-07 5.3000000000000001e-07 5.4000000000000002e-07 5.5000000000000003e-07 5.6000000000000004e-07 5.7000000000000005e-07 5.8000000000000006e-07 5.9000000000000007e-07 6.0000000000000008e-07 6.1000000000000009e-07 6.1999999999999999e-07 6.3e-07 6.4000000000000001e-07 6.5000000000000002e-07 6.6000000000000003e-07 6.7000000000000004e-07 6.8000000000000005e-07 6.9000000000000006e-07 7.0000000000000007e-07 7.1000000000000008e-07 7.2000000000000009e-07 7.3e-07 7.4000000000000001e-07 7.5000000000000002e-07 7.6000000000000003e-07 7.7000000000000004e-07 7.8000000000000005e-07 7.9000000000000006e-07 8.0000000000000007e-07 8.1000000000000008e-07 8.2000000000000009e-07 8.300000000000001e-07 8.4e-07 8.5000000000000001e-07 8.6000000000000002e-07 8.7000000000000003e-07 8.8000000000000004e-07 8.9000000000000006e-07 9.0000000000000007e-07 9.1000000000000008e-07 9.2000000000000009e-07 9.300000000000001e-07 9.4000000000000011e-07 9.5000000000000001e-07 9.6000000000000013e-07 9.7000000000000003e-07 9.8000000000000015e-07 9.9000000000000005e-07 1.0000000000000002e-06 1.0100000000000001e-06 1.02e-06 1.0300000000000001e-06 1.04e-06 1.0500000000000001e-06 1.06e-06 1.0700000000000001e-06 1.08e-06 1.0900000000000002e-06 1.1000000000000001e-06 1.1100000000000002e-06 1.1200000000000001e-06 1.13e-06 1.1400000000000001e-06 1.15e-06 1.1600000000000001e-06 1.17e-06 1.1800000000000001e-06 1.19e-06 1.2000000000000002e-06 1.2100000000000001e-06 1.2200000000000002e-06 1.2300000000000001e-06 1.24e-06 1.2500000000000001e-06 1.26e-06 1.2700000000000001e-06 1.28e-06 1.2900000000000001e-06 1.3e-06 1.3100000000000002e-06 1.3200000000000001e-06 1.3300000000000002e-06 1.3400000000000001e-06 1.35e-06 1.3600000000000001e-06 1.37e-06 1.3800000000000001e-06 1.39e-06 1.4000000000000001e-06 1.4100000000000001e-06 1.4200000000000002e-06 1.4300000000000001e-06 1.4400000000000002e-06 1.4500000000000001e-06 1.46e-06 1.4700000000000001e-06 1.48e-06 1.4900000000000001e-06 1.5e-06 1.5100000000000002e-06 1.5200000000000001e-06 1.5300000000000002e-06 1.5400000000000001e-06 1.5500000000000002e-06 1.5600000000000001e-06 1.57e-06 1.5800000000000001e-06 1.59e-06 1.6000000000000001e-06 1.61e-06 1.6200000000000002e-06 1.6300000000000001e-06 1.6400000000000002e-06 1.6500000000000001e-06 1.6600000000000002e-06 1.6700000000000001e-06 1.68e-06 1.6900000000000001e-06 1.7e-06 1.7100000000000001e-06 1.72e-06 1.7300000000000002e-06 1.7400000000000001e-06 1.7500000000000002e-06 1.7600000000000001e-06 1.7700000000000002e-06 1.7800000000000001e-06 1.79e-06 1.8000000000000001e-06 1.81e-06 1.8200000000000002e-06 1.8300000000000001e-06 1.8400000000000002e-06 1.8500000000000001e-06 1.8600000000000002e-06 1.8700000000000001e-06 1.8800000000000002e-06 1.8900000000000001e-06 1.9e-06 1.9099999999999999e-06 1.9200000000000003e-06 1.9300000000000002e-06 1.9400000000000001e-06 1.95e-06 1.9600000000000003e-06 1.9700000000000002e-06 1.9800000000000001e-06 1.99e-06 2.0000000000000003e-06 2.1000000000000002e-06 2.2000000000000001e-06 2.3e-06 2.4000000000000003e-06 2.5000000000000002e-06 2.6000000000000001e-06 2.7e-06 2.8000000000000003e-06 2.9000000000000002e-06 3.0000000000000001e-06 3.1000000000000004e-06 3.2000000000000003e-06 3.3000000000000002e-06 3.4000000000000001e-06 3.5000000000000004e-06 3.6000000000000003e-06 3.7000000000000002e-06 3.8e-06 3.8999999999999999e-06 4.0000000000000007e-06 4.1000000000000006e-06 4.2000000000000004e-06 4.3000000000000003e-06 4.4000000000000002e-06 4.5000000000000001e-06 4.6e-06 4.6999999999999999e-06 4.8000000000000006e-06 4.9000000000000005e-06 5.0000000000000004e-06 5.1000000000000003e-06 5.2000000000000002e-06 5.3000000000000001e-06 5.4e-06 5.5000000000000007e-06 5.6000000000000006e-06 5.7000000000000005e-06 5.8000000000000004e-06 5.9000000000000003e-06 6.0000000000000002e-06 6.1e-06 6.2000000000000008e-06 6.3000000000000007e-06 6.4000000000000006e-06 6.5000000000000004e-06 6.6000000000000003e-06 6.7000000000000002e-06 6.8000000000000001e-06 6.9000000000000009e-06 7.0000000000000007e-06 7.1000000000000006e-06 7.2000000000000005e-06 7.3000000000000004e-06 7.4000000000000003e-06 7.5000000000000002e-06 7.6000000000000001e-06 7.7000000000000008e-06 7.7999999999999999e-06 7.9000000000000006e-06 8.0000000000000013e-06 8.1000000000000004e-06 8.2000000000000011e-06 8.3000000000000002e-06 8.4000000000000009e-06 8.4999999999999999e-06 8.6000000000000007e-06 8.6999999999999997e-06 8.8000000000000004e-06 8.9000000000000012e-06 9.0000000000000002e-06 9.100000000000001e-06 9.2e-06 9.3000000000000007e-06 9.3999999999999998e-06 9.5000000000000005e-06 9.6000000000000013e-06 9.7000000000000003e-06 9.800000000000001e-06 9.9000000000000001e-06 1.0000000000000001e-05 1.1000000000000001e-05 1.2e-05 1.3000000000000001e-05 1.4000000000000001e-05 1.5e-05 1.6000000000000003e-05 1.7e-05 1.8e-05 1.9000000000000001e-05 2.0000000000000002e-05 2.1000000000000002e-05 2.2000000000000003e-05 2.3e-05 2.4000000000000001e-05 2.5000000000000001e-05 2.6000000000000002e-05 2.7000000000000002e-05 2.8000000000000003e-05 2.9e-05 3.0000000000000001e-05 3.1000000000000001e-05 3.2000000000000005e-05 3.3000000000000003e-05 3.4e-05 3.5000000000000004e-05 3.6000000000000001e-05 3.7000000000000005e-05 3.8000000000000002e-05 3.8999999999999999e-05 4.0000000000000003e-05 4.1e-05 4.2000000000000004e-05 4.3000000000000002e-05 4.4000000000000006e-05 4.5000000000000003e-05 4.6e-05 4.7000000000000004e-05 4.8000000000000001e-05 4.9000000000000005e-05 5.0000000000000002e-05 5.1000000000000006e-05 5.2000000000000004e-05 5.3000000000000001e-05 5.4000000000000005e-05 5.5000000000000002e-05 5.6000000000000006e-05 5.7000000000000003e-05 5.8e-05 5.9000000000000004e-05 6.0000000000000002e-05 6.1000000000000005e-05 6.2000000000000003e-05 6.3e-05 6.4000000000000011e-05 6.5000000000000008e-05 6.6000000000000005e-05 6.7000000000000002e-05 6.7999999999999999e-05 6.900000000000001e-05 7.0000000000000007e-05 7.1000000000000005e-05 7.2000000000000002e-05 7.2999999999999999e-05 7.400000000000001e-05 7.5000000000000007e-05 7.6000000000000004e-05 7.7000000000000001e-05 7.7999999999999999e-05 7.9000000000000009e-05 8.0000000000000007e-05 8.1000000000000004e-05 8.2000000000000001e-05 8.3000000000000012e-05 8.4000000000000009e-05 8.5000000000000006e-05 8.6000000000000003e-05 8.7000000000000001e-05 8.8000000000000011e-05 8.9000000000000008e-05 9.0000000000000006e-05 9.1000000000000003e-05 9.2e-05 9.3000000000000011e-05 9.4000000000000008e-05 9.5000000000000005e-05 9.6000000000000002e-05 9.7e-05 9.800000000000001e-05 9.9000000000000008e-05 0.0001'
  []
  line_search = bt
  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-10
  nl_max_its = 100
  l_tol = 1e-10
  l_max_its = 20
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = false
  petsc_options = '-snes_converged_reason -ksp_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
  petsc_options_value = 'preonly lu NONZERO'
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Outputs]
  checkpoint = true
  csv = true
  exodus = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
