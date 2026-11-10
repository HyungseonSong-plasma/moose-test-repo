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
    prop_names = 'legacy_mu legacy_D'
    prop_values = '1 1'
  []
  [electron_legacy_provider_alias]
    type = PhysicsSpeciesTransportAliasMaterial
    species_id = e
    mobility_source = legacy_mu
    diffusivity_source = legacy_D
  []
[]
