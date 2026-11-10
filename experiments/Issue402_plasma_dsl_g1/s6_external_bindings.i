# Add this input after the ten existing simulation inputs.
# It only checks species and internally resolved solver variables; it does not change the equations.
# Keep all existing inputs and simulation settings unchanged.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
        []
      []
    []
  []
[]
