# Synthetic surface-sticking P2 only. No claim of physical S6 wall semantics.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]
[Problem]
  solve = false
  kernel_coverage_check = false
[]
[FunctorMaterials]
  [state]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_g T_g Y_O2 Y_O'
    prop_values = '3.2e-5 300 1 0'
  []
  [surface_reactions]
    type = SurfaceReactionMaterial
    chemistry_file = json_surface_rate_p2.json
    density = rho_g
    temperature = T_g
    species = 'O2 O'
    mass_fractions = 'Y_O2 Y_O'
    active_reactions = 'H90'
  []
[]
[Postprocessors]
  [surface_progress]
    type = ElementAverageFunctorPostprocessor
    functor = R_H90
  []
  [O2_outward_mass_flux]
    type = ElementAverageFunctorPostprocessor
    functor = surface_mass_flux_O2
  []
  [O_outward_mass_flux]
    type = ElementAverageFunctorPostprocessor
    functor = surface_mass_flux_O
  []
  [total_outward_mass_flux]
    type = ElementAverageFunctorPostprocessor
    functor = surface_mass_flux_sum
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
