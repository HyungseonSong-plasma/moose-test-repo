# P14 Native --check-input-only synthetic FV creation discriminator.
# All eight reaction progress rates and coefficients are deliberately synthetic;
# this is NOT S6-417 Physics acceptance or P3. Assert 3x4 new FV Kernels.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 4
[]
[Problem]
  solve = false
  kernel_coverage_check = false
[]
[Variables]
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
    files = 'chemistry/oxygen_s6_common.json chemistry/oxygen_s6_417.json chemistry/oxygen_s6_p2_transport.json chemistry/oxygen_s6_p2_ions.json'
    [Transport]
      [Chemistry]
      []
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
          fem_potential = potential
        []
      []
    []
  []
[]
[FunctorMaterials]
  [synthetic_rate_and_carrier_providers]
    type = ADGenericFunctorMaterial
    prop_names = 'R_EI02 R_EI17 R_EI415 R_EI401 R_EI407 R_EI2069 R_H25 R_EI417 delta_epsilon_EI02_eV delta_epsilon_EI17_eV carrier_one'
    prop_values = '1 1 1 1 1 1 1 1 0.2 0.1 1'
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
