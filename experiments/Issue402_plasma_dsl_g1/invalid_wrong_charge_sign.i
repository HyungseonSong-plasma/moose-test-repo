# Deliberately invalid Continuity option contract; check-input must fail closed.
[Physics]
  [Plasmas]
    files = plasma_species_only.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p'
          fem_charge_numbers = '1'
          fvm_charge_numbers = '1'

        []
      []
    []
  []
[]
