# Species are assigned to the opposite discretization of their derived existing variables.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'O2p'
          fvm_species = 'e'
        []
      []
    []
  []
[]
