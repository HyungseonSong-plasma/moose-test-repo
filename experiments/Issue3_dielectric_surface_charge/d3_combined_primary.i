# Issue #3 D3 combined primary-current dielectric charging discriminator.
#
# One FV cell of volume 1 m^3 has one dielectric face of area 1 m^2.
# Ion and primary-electron wall number fluxes are the ONLY particle-loss owners.
# The exact same functors also build the signed surface current:
#
#   j_to_surface = +e*Gamma_i - e*Gamma_e
#   d(sigma_s)/dt = j_to_surface
#
# Therefore, with no SEE and no other open/current boundary,
#
#   Delta Q_volume + Delta Q_surface = 0.

[Mesh]
  type = GeneratedMesh
  dim = 1
  xmin = 0
  xmax = 1
  nx = 1
[]

[Variables]
  [log_ni]
    type = MooseVariableFVReal
    initial_condition = -17.913538455038942
  []
  [log_ne]
    type = MooseVariableFVReal
    initial_condition = -24.8815988940131
  []
[]

[Functions]
  [zero_potential]
    type = ParsedFunction
    expression = '0'
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'ion_mobility T_g mean_energy'
    prop_values = '0.0 300.0 3.0'
    block = 0
  []

  [ion_density]
    type = ADParsedFunctorMaterial
    property_name = n_i_physical
    functor_names = 'log_ni'
    functor_symbols = 'u'
    expression = '6.02214076e23*exp(u)'
    block = 0
  []

  [electron_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'log_ne'
    functor_symbols = 'u'
    expression = '6.02214076e23*exp(u)'
    block = 0
  []

  [ion_wall_flux]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = n_i_physical
    potential = zero_potential
    mobility = ion_mobility
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.032
    sticking = 1.0
    ion_temperature_eV = 0.0
    migration_gate_smoothing_width = 0.0
    block = 0
  []

  [electron_wall_flux]
    type = PhysicsElectronWallFluxMaterial
    electron_density = n_e_physical
    mean_energy = mean_energy
    sticking = 1.0
    block = 0
  []

  [ion_surface_current]
    type = ADParsedFunctorMaterial
    property_name = ion_surface_current_density
    functor_names = 'ion_wall_number_flux'
    functor_symbols = 'Gamma_i'
    expression = '1.602176634e-19*Gamma_i'
    block = 0
  []

  [electron_surface_current]
    type = ADParsedFunctorMaterial
    property_name = electron_surface_current_density
    functor_names = 'electron_wall_number_flux'
    functor_symbols = 'Gamma_e'
    expression = '-1.602176634e-19*Gamma_e'
    block = 0
  []

  [net_surface_current]
    type = ADParsedFunctorMaterial
    property_name = net_surface_current_density
    functor_names = 'ion_surface_current_density electron_surface_current_density'
    functor_symbols = 'ji je'
    expression = 'ji+je'
    block = 0
  []

  [volume_charge_density]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = 'n_i_physical n_e_physical'
    functor_symbols = 'ni ne'
    expression = '1.602176634e-19*(ni-ne)'
    block = 0
  []
[]

[FVKernels]
  [ion_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ni
  []
  [electron_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ne
  []
[]

[FVBCs]
  [ion_dielectric_loss]
    type = FVFunctorNeumannBC
    variable = log_ni
    functor = ion_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = right
  []
  [electron_dielectric_loss]
    type = FVFunctorNeumannBC
    variable = log_ne
    functor = electron_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = right
  []
[]

[UserObjects]
  [surface_charge_state]
    type = PhysicsSurfaceChargeState
    boundary = right
    surface_current_density = net_surface_current_density
    initial_surface_charge = 0
    execute_on = TIMESTEP_END
  []
[]

[Postprocessors]
  [ion_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_i_physical
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e_physical
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [volume_charge]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density_C_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [ion_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = ion_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [electron_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = electron_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [net_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = net_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []

  [surface_total_charge]
    type = PhysicsSurfaceChargeStatePostprocessor
    surface_charge_state = surface_charge_state
    quantity = total_charge
    execute_on = TIMESTEP_END
  []
  [surface_area]
    type = PhysicsSurfaceChargeStatePostprocessor
    surface_charge_state = surface_charge_state
    quantity = surface_area
    execute_on = TIMESTEP_END
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 1.0e-7
  end_time = 1.0e-7
  nl_abs_tol = 1.0e-12
  nl_rel_tol = 1.0e-10
  nl_max_its = 30
[]

[Outputs]
  csv = true
[]
