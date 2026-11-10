# Previously incomplete coefficient vectors; now both options are forbidden.
# No generated kernel or missing mesh block may mask the deprecated-key error.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fvm_species = 'O2p'
          mobility = 'electron_mobility'
          diffusivity = 'electron_diffusion'
        []
      []
    []
  []
[]
