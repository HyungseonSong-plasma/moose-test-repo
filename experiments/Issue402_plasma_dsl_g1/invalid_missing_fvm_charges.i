# Deliberately invalid Continuity option contract; check-input must fail closed.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p'
          fem_potential = log_ne
          fem_charge_numbers = '-1'

        []
      []
    []
  []
[]
