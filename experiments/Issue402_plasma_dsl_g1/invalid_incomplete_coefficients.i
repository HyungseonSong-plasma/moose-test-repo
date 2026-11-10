# Deprecated user coefficient options are no longer accepted; fail closed.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p'
          fem_potential = log_ne
          mobility = 'electron_mobility'
          diffusivity = 'electron_diffusion'
          fem_charge_numbers = '-1'
          fvm_charge_numbers = '1'

        []
      []
    []
  []
[]
