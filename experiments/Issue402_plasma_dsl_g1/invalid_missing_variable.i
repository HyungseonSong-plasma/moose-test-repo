# A listed solver variable does not exist.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          owner_mode = external
          fem_species = 'e'
          fvm_species = 'O2p'
          variables = 'missing_fe u_fv'
        []
      []
    []
  []
[]
