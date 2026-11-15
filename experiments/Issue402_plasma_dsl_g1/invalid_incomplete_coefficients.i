# Negative P2: the retired positional coefficient vectors no longer belong
# to Continuity. e is JSON-initialized by the standalone transport base;
# this overlay must fail on forbidden mobility, not missing e initial density.
# Keep both obsolete option names to preserve the historical regression.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          mobility = 'electron_mobility'
          diffusivity = 'electron_diffusion'
        []
      []
    []
  []
[]
