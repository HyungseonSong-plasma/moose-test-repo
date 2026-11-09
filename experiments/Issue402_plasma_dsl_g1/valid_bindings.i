# Issue #402 G1 positive: external binding; numerical objects already exist.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          owner_mode = external
          fem_species = 'e'
          fvm_species = 'O2p'
          variables = 'u_fe u_fv'
        []
      []
    []
  []
[]
