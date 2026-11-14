# P2 JSON-owned e/O2p binding, not an old external [Variables] overlay.
# The explicit source is one cohesive JSON catalogue; solver states and ICs
# are created exactly once by DriftDiffusion Continuity.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 4
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
