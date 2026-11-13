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
[Physics]
  [Plasmas]
    files = json_surface_rate_p2.json
    pressure = 1.333223684
    temperature = 300
    model = ideal_gas
  []
[]
[FunctorMaterials]
  [state]
    type = ADGenericFunctorMaterial
    prop_names = 'Y_O2 Y_O'
    prop_values = '1 0'
  []
  [surface_reactions]
    type = SurfaceReactionMaterial
    chemistry_file = json_surface_rate_p2.json
    density = rho_g
    temperature = T
    species = 'O2'
    mass_fractions = 'Y_O2'
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
