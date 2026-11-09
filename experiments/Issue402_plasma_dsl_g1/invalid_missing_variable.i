# A listed solver variable does not exist.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fvm_species = 'O2p'
          variables = 'missing_fe u_fv'
        []
      []
    []
  []
[]
