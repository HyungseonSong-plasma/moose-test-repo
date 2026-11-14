# Deliberately invalid Continuity option contract; check-input must fail closed.
[Physics]
  [Plasmas]
    files = plasma_species_initial_p2.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p'
          fem_kernel_names = 'ne_transport'

        []
      []
    []
  []
[]
