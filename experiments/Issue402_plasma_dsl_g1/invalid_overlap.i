# Same species cannot be FEM and FV simultaneously.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          owner_mode = external
          fem_species = 'e O2p'
          fvm_species = 'O2p'
          variables = 'u_fe u_fv u_fe'
        []
      []
    []
  []
[]
