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
[Variables]
  [w_O2]
    type = MooseVariableFVReal
  []
  [w_O]
    type = MooseVariableFVReal
  []
[]
[Physics]
  [Plasmas]
    files = json_surface_rate_p2.json
    pressure = 1.333223684
    temperature = 300
    state_model = ideal_gas
    inlet_boundaries = left
    sccm = 100
  []
[]
[FunctorMaterials]
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
  [initial_gas_density]
    type = ElementAverageFunctorPostprocessor
    functor = rho_g_initial
  []
  [inlet_gas_density]
    type = ElementAverageFunctorPostprocessor
    functor = rho_g_inlet
  []
  [inlet_mean_molar_mass]
    type = ElementAverageFunctorPostprocessor
    functor = M_mix_inlet
  []
  [volume_initial_O2]
    type = ElementAverageFunctorPostprocessor
    functor = Y_O2_initial_vol
  []
  [inlet_O2]
    type = ElementAverageFunctorPostprocessor
    functor = Y_O2_inlet
  []
  [inlet_O]
    type = ElementAverageFunctorPostprocessor
    functor = Y_O_inlet
  []
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
