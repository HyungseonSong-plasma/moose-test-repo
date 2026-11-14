# P2-only variable binding: the Chemistry JSON owns electron/ion
# initial_number_density [1/m^3] and generated solver variables.
# Intentionally standalone: legacy baseline.i declares the same variables
# externally and cannot be overlaid with this JSON-owned continuity action.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 8
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
          fem_species = 'e'
          fvm_species = 'O2p'
        []
      []
    []
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
