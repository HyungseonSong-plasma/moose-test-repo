# Issue #3 D2 controlled dielectric charging discriminator.
#
# Sign convention:
#   n: plasma -> dielectric surface
#   Gamma_e,to_surface > 0: primary electrons leave plasma
#   j_to_surface = -e * Gamma_e,to_surface
#   d(sigma_s)/dt = j_to_surface
#
# This test uses the canonical PhysicsElectronWallFluxMaterial with a fixed
# electron density and fixed mean energy. No ions or SEE are present.

[Mesh]
  type = GeneratedMesh
  dim = 1
  xmin = 0
  xmax = 1
  nx = 1
[]

# Inert FV variable: requests FaceInfo construction without participating in
# the physics. The surface-charge state and wall-flux functors remain the only
# owners of the D2 charging law.
[AuxVariables]
  [face_info_trigger]
    type = MooseVariableFVReal
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'n_e mean_energy'
    prop_values = '1.0e16 3.0'
    block = 0
  []

  [electron_wall_flux]
    type = PhysicsElectronWallFluxMaterial
    electron_density = n_e
    mean_energy = mean_energy
    sticking = 1.0
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
[]

[UserObjects]
  [surface_charge_state]
    type = PhysicsSurfaceChargeState
    boundary = right
    surface_current_density = electron_surface_current_density
    initial_surface_charge = 0
    execute_on = TIMESTEP_END
  []
[]

[Postprocessors]
  [electron_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = electron_surface_current_density
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
