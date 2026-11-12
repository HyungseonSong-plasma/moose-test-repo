# These inputs validate objects from the small example; they do not add equations.
[Physics]
  [Plasmas]
    files = plasma_noop_control.json
    [Transport]
      [Chemistry]
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
