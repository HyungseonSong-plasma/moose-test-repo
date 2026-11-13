# Synthetic P2 only: demonstrate missing log_e, log_e_energy, and potential.
# Do not use these example initial values as physical S6 data.
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
    files = plasma_species_initial_p2.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = e
          fem_potential = potential
        []
        [Energy]
          fem_species = e
        []
      []
    []
    [Poisson]
      fem_potential = potential
      initial_potential_V = 0
    []
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
