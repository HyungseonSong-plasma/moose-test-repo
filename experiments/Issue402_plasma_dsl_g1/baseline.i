# Issue #402 G1: immutable two-field physical-equation control.
# Both diffusion equations are built explicitly here. Plasma DSL does NOT
# generate or modify any equations in this opt-in binding-only pilot.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 8
[]
[Variables]
  [u_fe]
    family = LAGRANGE
    order = FIRST
  []
  [u_fv]
    type = MooseVariableFVReal
  []
[]
[Kernels]
  [fe_diffusion]
    type = Diffusion
    variable = u_fe
  []
[]
[FVKernels]
  [fv_diffusion]
    type = FVDiffusion
    variable = u_fv
    coeff = 1
  []
[]
[BCs]
  [fe_left]
    type = DirichletBC
    variable = u_fe
    boundary = left
    value = 0
  []
  [fe_right]
    type = DirichletBC
    variable = u_fe
    boundary = right
    value = 1
  []
[]
[FVBCs]
  [fv_left]
    type = FVDirichletBC
    variable = u_fv
    boundary = left
    value = 0
  []
  [fv_right]
    type = FVDirichletBC
    variable = u_fv
    boundary = right
    value = 1
  []
[]
[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1e-10
  nl_abs_tol = 1e-12
[]
[Outputs]
  exodus = true
[]
