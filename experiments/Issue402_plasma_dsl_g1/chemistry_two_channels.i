# Synthetic **P2 construction only**; EI-405/EI-406 identifiers here
# are illustrative, not verified physical reaction-channel assignments.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 4
[]
[Variables]
  [log_e]
    family = LAGRANGE
    order = FIRST
    initial_condition = 0
  []
  [log_energy]
    family = LAGRANGE
    order = FIRST
    initial_condition = 0
  []
  [potential]
    family = LAGRANGE
    order = FIRST
    initial_condition = 0
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
    files = plasma_two_channels.json
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
          variable = log_energy
        []
      []
    []
  []
[]
[FunctorMaterials]
  [synthetic_progress_and_transport]
    type = ADGenericFunctorMaterial
    prop_names = 'R_EI405 R_EI406 mu_test D_test'
    prop_values = '1 2 1 1'
  []
  [electron_coefficients]
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
