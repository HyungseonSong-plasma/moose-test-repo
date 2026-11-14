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
  [smoke_functor_value]
    family = MONOMIAL
    order = CONSTANT
  []
[]

# Exercise a built-in MOOSE AuxKernel through an AD Functor instead of
# depending on a one-off PhysicsApp background-density class.
[FunctorMaterials]
  [smoke_constant_functor]
    type = ADGenericFunctorMaterial
    prop_names = 'smoke_functor'
    prop_values = '1.0'
  []
[]

[Kernels]
  [diffusion]
    type = Diffusion
    variable = u
  []
[]

[AuxKernels]
  [sample_smoke_functor]
    type = FunctorAux
    variable = smoke_functor_value
    functor = smoke_functor
    execute_on = 'INITIAL TIMESTEP_END'
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
