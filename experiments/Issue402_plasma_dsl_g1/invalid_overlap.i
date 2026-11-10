# A species cannot use both finite-element and finite-volume variables.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e O2p'
          fvm_species = 'O2p'
        []
      []
    []
  []
[]
