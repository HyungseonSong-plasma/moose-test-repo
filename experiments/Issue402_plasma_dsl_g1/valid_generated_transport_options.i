# P2 construction-only control for the option-first FEM builder.
# Existing baseline.i provides log_ne; the following named constants are
# test-only coefficient providers. Not an accepted plasma model or P3 input.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fem_potential = log_ne
          fem_charge_numbers = '-1'
        []
      []
    []
  []
[]

[FunctorMaterials]
  [controlled_species_coefficients]
    type = ADGenericFunctorMaterial
    prop_names = 'e_mobility e_diffusivity'
    prop_values = '1 1'
  []
[]
