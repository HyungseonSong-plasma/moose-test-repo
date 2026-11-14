# Negative P2: Energy only supports FEM species e.
# Do not add the retired 'variable' key: it would mask the intended error.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Energy]
          fem_species = 'O2p'
        []
      []
    []
  []
[]
