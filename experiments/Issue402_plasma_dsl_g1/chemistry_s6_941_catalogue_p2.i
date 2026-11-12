# P2 construction check of the archived S6-941 reaction IDs.
# Rate values below are SYNTHETIC; not a physical run, not an S6 source cutover.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 4
[]
[Variables]
  [log_e]
    family = LAGRANGE
    order = FIRST
  []
  [log_e_energy]
    family = LAGRANGE
    order = FIRST
  []
  [potential]
    family = LAGRANGE
    order = FIRST
  []
[]
[Kernels]
  [potential_probe]
    type = Diffusion
    variable = potential
  []
[]
[Physics]
  [Plasmas]
    files = 'chemistry/oxygen_s6_common.json chemistry/oxygen_s6_941.json'
    [Transport]
      [Chemistry]
      []
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fem_potential = potential
        []
        [Energy]
          fem_species = 'e'
        []
      []
    []
  []
[]
[FunctorMaterials]
  [synthetic_rate_and_transport_providers]
    type = ADGenericFunctorMaterial
    prop_names = 'R_EI02 R_EI17 R_EI415 R_EI401 R_EI407 R_EI2069 R_H25 R_EI941 delta_epsilon_EI02_eV delta_epsilon_EI17_eV mu_test D_test'
    prop_values = '1 1 1 1 1 1 1 1 0.2 0.1 1 1'
  []
  [ei02_signed_energy_change]
    type = ADParsedFunctorMaterial
    property_name = signed_delta_epsilon_EI02_eV
    functor_names = 'delta_epsilon_EI02_eV'
    functor_symbols = 'loss'
    expression = '-loss'
  []
  [ei17_signed_energy_change]
    type = ADParsedFunctorMaterial
    property_name = signed_delta_epsilon_EI17_eV
    functor_names = 'delta_epsilon_EI17_eV'
    functor_symbols = 'loss'
    expression = '-loss'
  []
  [electron_transport]
    type = SpeciesTransportAliasMaterial
    species_id = e
    mobility_source = mu_test
    diffusivity_source = D_test
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
