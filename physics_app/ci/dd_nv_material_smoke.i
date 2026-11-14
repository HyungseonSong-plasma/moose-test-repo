# P2-only construction check. No physical solve / P3.
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
  [controlled_fields]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en_solved T_g p Y_A Y_B'
    prop_values = '3 300 100 0.5 0.5'
  []
  [electron_constant]
    type = DDMaterial
    species_id = e
    model = constant
    mobility = 0.25
    diffusivity = 0.125
  []
  [ion_table]
    type = DDMaterial
    species_id = O2p
    model = lookup
    table_file = electron_energy_lookup_response_smoke_table.txt
    table_units = physical
    bounds_policy = error
  []
  [mixture_collision_data]
    type = NVMaterial
    temperature = T_g
    pressure = p
    transport_data_file = plasma_closures_heavy_transport.txt
    species = 'A B'
    mass_fractions = 'Y_A Y_B'
  []
[]
[Postprocessors]
  [electron_mu]
    type = ElementAverageFunctorPostprocessor
    functor = e_mobility
  []
  [electron_D]
    type = ElementAverageFunctorPostprocessor
    functor = e_diffusivity
  []
  [electron_energy_mu]
    type = ElementAverageFunctorPostprocessor
    functor = electron_energy_mobility
  []
  [ion_mu]
    type = ElementAverageFunctorPostprocessor
    functor = O2p_mobility
  []
  [ion_D]
    type = ElementAverageFunctorPostprocessor
    functor = O2p_diffusivity
  []
  [heavy_Dmix_A]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_A
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
