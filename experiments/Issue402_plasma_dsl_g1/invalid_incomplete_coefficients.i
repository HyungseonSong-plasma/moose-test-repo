# Negative option contract: direct mobility/diffusivity vectors are retired.
# The source JSON owns transport coefficients. Overlay the modern standalone
# valid_generated_transport_json_p2.i so missing JSON IC/external variables
# cannot mask the intended unsupported-option rejection.
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
