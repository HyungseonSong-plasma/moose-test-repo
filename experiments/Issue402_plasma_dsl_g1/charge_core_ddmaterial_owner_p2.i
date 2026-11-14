# Issue402 P2: DDTransportMaterial publishes O2p/Om/Op mobility and diffusivity,
# while PhysicsPlasmaChargeDensityMaterial owns all charge-related Functors.
# The retired PlasmaChargeTransportMaterial is deliberately absent.
# Synthetic values; --check-input only, not a Native P3 simulation.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]
[Problem]
  kernel_coverage_check = false
  solve = false
[]
[FunctorMaterials]
  [native_coefficients]
    type = ADGenericFunctorMaterial
    prop_names = 'rho ne w_O2p w_Om w_Op ion_mobility ion_diffusion negative_ion_mobility negative_ion_diffusion atomic_positive_ion_mobility atomic_positive_ion_diffusion'
    prop_values = '1 1e16 1e-4 1e-5 1e-5 0.002 0.003 0.004 0.005 0.006 0.007'
  []
  [O2p_coefficients]
    type = DDTransportMaterial
    species_id = O2p
    model = functor
    mobility_source = ion_mobility
    diffusivity_source = ion_diffusion
  []
  [Om_coefficients]
    type = DDTransportMaterial
    species_id = Om
    model = functor
    mobility_source = negative_ion_mobility
    diffusivity_source = negative_ion_diffusion
  []
  [Op_coefficients]
    type = DDTransportMaterial
    species_id = Op
    model = functor
    mobility_source = atomic_positive_ion_mobility
    diffusivity_source = atomic_positive_ion_diffusion
  []
  [charge_density]
    type = PhysicsPlasmaChargeDensityMaterial
    density = rho
    electron_density = ne
    ion_ids = 'O2p Om Op'
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_molar_masses = '0.032 0.016 0.016'
    ion_charges = '1 -1 1'
  []
[]
[Postprocessors]
  [O2p_mu]
    type = ElementAverageFunctorPostprocessor
    functor = O2p_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_D]
    type = ElementAverageFunctorPostprocessor
    functor = O2p_diffusivity
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_mu]
    type = ElementAverageFunctorPostprocessor
    functor = Om_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_D]
    type = ElementAverageFunctorPostprocessor
    functor = Om_diffusivity
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_mu]
    type = ElementAverageFunctorPostprocessor
    functor = Op_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_D]
    type = ElementAverageFunctorPostprocessor
    functor = Op_diffusivity
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_source_probe]
    type = ElementAverageFunctorPostprocessor
    functor = poisson_charge_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [number_density_O2p]
    type = ElementAverageFunctorPostprocessor
    functor = ion_number_density_O2p
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_density_probe]
    type = ElementAverageFunctorPostprocessor
    functor = charge_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
