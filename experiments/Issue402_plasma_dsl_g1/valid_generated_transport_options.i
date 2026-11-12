# P2 construction-only control for the option-first FEM builder.
# Existing baseline.i provides log_e; the following named constants are
# test-only coefficient providers. Not an accepted plasma model or P3 input.
[Physics]
  [Plasmas]
    files = plasma_species_only.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fem_potential = log_e
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

# P2-only TimeKernel needs the TIME vector tag. Keep baseline/production untouched.
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
