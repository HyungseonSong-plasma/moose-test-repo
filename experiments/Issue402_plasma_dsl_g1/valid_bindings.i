# Both solver variables are already defined in the main input.
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
