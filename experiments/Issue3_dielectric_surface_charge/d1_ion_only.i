# Issue #3 D1 controlled dielectric charging discriminator.
#
# Sign convention:
#   n: plasma -> dielectric surface
#   Gamma_i,to_surface > 0: ion particles leave plasma
#   j_to_surface = +e * Gamma_i,to_surface
#   d(sigma_s)/dt = j_to_surface
#
# This test deliberately disables electrostatic migration (mu_i = 0) so the
# independently reconstructable thermal-sticking flux is the only current.

[Mesh]
  type = GeneratedMesh
  dim = 1
  xmin = 0
  xmax = 1
  nx = 1
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
    prop_names = 'n_i ion_mobility T_g'
    prop_values = '1.0e16 0.0 300.0'
    block = 0
  []

  [ion_wall_flux]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = n_i
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

  [ion_surface_current]
    type = ADParsedFunctorMaterial
    property_name = ion_surface_current_density
    functor_names = 'ion_wall_number_flux'
    functor_symbols = 'Gamma_i'
    expression = '1.602176634e-19*Gamma_i'
    block = 0
  []
[]

[UserObjects]
  [surface_charge_state]
    type = PhysicsSurfaceChargeState
    boundary = right
    surface_current_density = ion_surface_current_density
    initial_surface_charge = 0
    execute_on = TIMESTEP_END
  []
[]

[Postprocessors]
  [ion_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = ion_surface_current_density
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

  [surface_average_charge]
    type = PhysicsSurfaceChargeStatePostprocessor
    surface_charge_state = surface_charge_state
    quantity = average_surface_charge
    execute_on = TIMESTEP_END
  []
[]

[Problem]
  solve = false
[]

[Executioner]
  type = Transient
  dt = 1.0e-7
  end_time = 1.0e-7
[]

[Outputs]
  csv = true
[]
