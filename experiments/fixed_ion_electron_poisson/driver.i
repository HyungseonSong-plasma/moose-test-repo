# Minimal fixed-ion electron-energy <-> Poisson prototype.
# No Gummel Action, no heavy-ion evolution, no heavy electromigration correction.
# Electron-energy advances once at TIMESTEP_BEGIN; Poisson solves once at TIMESTEP_END.

[Mesh]
  coord_type = RZ
  rz_coord_axis = Y

  [main]
    type = FileMeshGenerator
    file = '../Issue91_real_qvt_r3/r3_e0/qvt.msh'
  []
  [plasma_only]
    type = BlockDeletionGenerator
    input = main
    operation = keep
    block = plasma
  []
[]

[Problem]
  solve = false
  kernel_coverage_check = false
[]

[MultiApps]
  [electron_energy]
    type = TransientMultiApp
    input_files = 'electron_energy.i'
    execute_on = TIMESTEP_BEGIN
    no_restore = true
  []

  [poisson]
    type = TransientMultiApp
    input_files = 'poisson.i'
    execute_on = TIMESTEP_END
    no_restore = true
  []
[]

[Transfers]
  # Uses the previous Poisson state for the next electron-energy pseudo step.
  [potential_to_electron]
    type = MultiAppCopyTransfer
    from_multi_app = poisson
    to_multi_app = electron_energy
    source_variable = potential
    variable = potential_from_poisson
  []

  # Uses the newly advanced electron density in the Poisson solve of this step.
  [electron_to_poisson]
    type = MultiAppCopyTransfer
    from_multi_app = electron_energy
    to_multi_app = poisson
    source_variable = n_e
    variable = n_e_from_electron
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler

  dt = 1.0e-9
  dtmin = 1.0e-9
  dtmax = 1.0e-9
  num_steps = 10
  end_time = 1.0e-8
  timestep_tolerance = 1.0e-18
[]

[Outputs]
  console = true
[]
