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
        []
        [Energy]
          fem_species = 'e'
          variable = log_e
        []
      []
    []
    [Poisson]
      potential_variable = log_e
    []
    [Maxwell]
      field_real = log_e
      field_imag = u_rf_imag
      frequency_hz = 13560000
    []
  []
[]
