[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 1
[]

[Variables]
  [u]
  []
[]

[AuxVariables]
  [background_density]
  []
[]

[Kernels]
  [diffusion]
    type = Diffusion
    variable = u
  []
[]

[AuxKernels]
  [background_density]
    type = PhysicsBackgroundDensity
    variable = background_density
  []
[]

[BCs]
  [left]
    type = DirichletBC
    variable = u
    boundary = left
    value = 0
  []
  [right]
    type = DirichletBC
    variable = u
    boundary = right
    value = 0
  []
[]

[Executioner]
  type = Steady
[]

[Outputs]
  exodus = false
  csv = false
[]
