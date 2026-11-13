# Synthetic, source-bound P2: all four owners share LIVE Y_i(t,x).
# Only a syntax/ownership gate; no P3 physics or historical numeric equivalence.
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
  [w_Op]
    type = MooseVariableFVReal
  []
[]
[Physics]
  [Plasmas]
    files = json_species_live_all4_p2.json
    pressure = 1.333223684
    temperature = 300
    model = ideal_gas
    initialize_species_mass_fractions = true
    inlet_boundaries = left
    inlet_bc_model = dirichlet
    [Transport]
      [NavierStokes]
      []
    []
  []
[]
[FunctorMaterials]
  [electron_state]
    type = ADGenericFunctorMaterial
    prop_names = 'n_e T_e'
    prop_values = '1e15 10000'
  []
  [heavy_progress]
    type = HRateCoefMaterial
    chemistry_file = json_species_live_all4_p2.json
    density = rho_g
    temperature = T
    species = 'O2 O Op'
    mass_fractions = 'Y_O2 Y_O Y_Op'
    active_reactions = 'H91'
  []
  [surface_progress]
    type = SurfaceReactionMaterial
    chemistry_file = json_species_live_all4_p2.json
    density = rho_g
    temperature = T
    species = 'O2'
    mass_fractions = 'Y_O2'
    active_reactions = 'H90'
  []
  [charge]
    type = PhysicsPlasmaChargeDensityMaterial
    density = rho_g
    electron_density = n_e
    ion_ids = 'Op'
    ion_mass_fractions = 'Y_Op'
    ion_molar_masses = '0.016'
    ion_charges = '1'
  []
[]
[Postprocessors]
  [heavy_rate]
    type = ElementAverageFunctorPostprocessor
    functor = R_H91
  []
  [surface_rate]
    type = ElementAverageFunctorPostprocessor
    functor = R_H90
  []
  [mix_diffusivity_O2]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O2
  []
  [space_charge_density]
    type = ElementAverageFunctorPostprocessor
    functor = charge_density
  []
  [live_Y_O2]
    type = ElementAverageFunctorPostprocessor
    functor = Y_O2
  []
  [live_Y_Op]
    type = ElementAverageFunctorPostprocessor
    functor = Y_Op
  []
  [inlet_Y_O2]
    type = ElementAverageFunctorPostprocessor
    functor = Y_O2_inlet
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
