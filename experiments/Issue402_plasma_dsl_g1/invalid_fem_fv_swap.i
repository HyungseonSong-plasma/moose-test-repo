# FEM 'e' incorrectly mapped to FV variable and vice versa.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          owner_mode = external
          fem_species = 'e'
          fvm_species = 'O2p'
          variables = 'u_fv u_fe'
        []
      []
    []
  []
[]
