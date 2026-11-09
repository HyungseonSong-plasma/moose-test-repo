# Missing original solved variable, cannot silently create one.
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
