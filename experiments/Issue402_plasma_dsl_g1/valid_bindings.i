# Solver variable names are derived internally: e -> log_e, O2p -> log_O2p.
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
