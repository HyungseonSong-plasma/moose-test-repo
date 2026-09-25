[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [electron_density]
    type = MooseVariableFVReal
    initial_condition = 1
  []
  [electron_energy]
    type = MooseVariableFVReal
    initial_condition = 1
  []
[]

[AuxVariables]
  [potential_from_poisson]
    type = MooseVariableFVReal
    initial_condition = 0
  []
[]

[GummelIteration]
  [electron_poisson]
    poisson_multiapp = poisson
    poisson_input_file = gummel_action_poisson.i
    electron_state_variables = 'electron_density electron_energy'
    electron_to_poisson_source_variables = 'electron_density electron_energy'
    electron_to_poisson_variables = 'electron_density_frozen electron_energy_frozen'
    poisson_to_electron_source_variables = 'potential_plasma'
    poisson_to_electron_variables = 'potential_from_poisson'
    poisson_transformed_variables = 'potential_plasma'
    relaxation_factor = 0.45
    no_restore = true
    manage_convergence = false
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
