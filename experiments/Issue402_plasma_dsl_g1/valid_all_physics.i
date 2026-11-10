# These inputs validate objects from the small example; they do not add equations.
[Physics]
  [Plasmas]
    [Transport]
      [Chemistry]
        reaction_ids = 'example_reaction'
        reaction_progress = 'example_reaction_rate'
      []
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fvm_species = 'O2p'
          variables = 'u_fe u_fv'
        []
        [Energy]
          fem_species = 'e'
          variable = u_fe
        []
      []
    []
    [Poisson]
      potential_variable = u_fe
    []
    [Maxwell]
      field_real = u_fe
      field_imag = u_rf_imag
      frequency_hz = 13560000
    []
  []
[]
