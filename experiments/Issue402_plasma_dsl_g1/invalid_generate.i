# This check cannot create equations or variables.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          owner_mode = generate
          fem_species = 'e'
          fvm_species = 'O2p'
          variables = 'u_fe u_fv'
        []
      []
    []
  []
[]
