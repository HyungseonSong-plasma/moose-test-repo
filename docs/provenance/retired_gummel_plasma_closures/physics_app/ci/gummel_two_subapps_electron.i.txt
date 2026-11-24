[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
  []
  [mean_en]
    type = MooseVariableFVReal
    initial_condition = 5.73276e16
  []
[]

[AuxVariables]
  [phi]
    type = MooseVariableFVReal
    initial_condition = 0
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
