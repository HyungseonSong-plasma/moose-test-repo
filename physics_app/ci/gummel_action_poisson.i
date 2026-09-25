[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [potential_plasma]
    type = MooseVariableFVReal
    initial_condition = 0
  []
[]

[AuxVariables]
  [electron_density_frozen]
    type = MooseVariableFVReal
    initial_condition = 1
  []
  [electron_energy_frozen]
    type = MooseVariableFVReal
    initial_condition = 1
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
