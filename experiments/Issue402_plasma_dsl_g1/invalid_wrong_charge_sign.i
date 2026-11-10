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
          mobility = 'electron_mobility ion_mobility'
          diffusivity = 'electron_diffusion ion_diffusion'
          fem_charge_numbers = '1'
          fvm_charge_numbers = '1'

        []
      []
    []
  []
[]
