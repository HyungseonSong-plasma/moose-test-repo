# P2 construction-only control for the option-first FEM builder.
# Existing baseline.i provides log_ne; literal 1 is a test-only constant
# coefficient. This is NOT an accepted physical plasma model or P3 input.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fem_potential = log_ne
          mobility = '1'
          diffusivity = '1'
          fem_charge_numbers = '-1'
        []
      []
    []
  []
[]
