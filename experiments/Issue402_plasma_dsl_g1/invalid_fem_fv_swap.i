# Each species points to a solver variable of the wrong type.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fvm_species = 'O2p'
          variables = 'u_fv u_fe'
        []
      []
    []
  []
[]
