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

# DDEnergyEq resolves this variable internally from fem_species = 'e'.
[Variables]
  [log_e_energy]
    family = LAGRANGE
    order = FIRST
  []
[]
[Kernels]
  [energy_integrity_probe]
    type = Diffusion
    variable = log_e_energy
  []
[]
[BCs]
  [energy_integrity_left]
    type = DirichletBC
    variable = log_e_energy
    boundary = left
    value = 0
  []
  [energy_integrity_right]
    type = DirichletBC
    variable = log_e_energy
    boundary = right
    value = 0
  []
[]
