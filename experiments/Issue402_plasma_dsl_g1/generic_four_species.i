# P2: four JSON-owned species states, no duplicate external Variables/ICs.
# Continuity generates FEM log_e and FV log_O2p/log_Om/log_Op from the
# single species catalogue; their derived names remain part of the contract.
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
          fvm_species = 'O2p Om Op'
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
