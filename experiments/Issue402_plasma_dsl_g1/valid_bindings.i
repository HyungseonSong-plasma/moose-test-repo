# Solver variable names are derived internally: e -> log_ne, O2p -> log_ni.
[Physics]
  [Plasmas]
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
