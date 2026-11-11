# The two diffusion equations are defined here.
# Checking species variables must not change either equation.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 8
[]
[Variables]
  [log_e]
    family = LAGRANGE
    order = FIRST
  []
  [log_O2p]
    type = MooseVariableFVReal
  []
  [u_rf_imag]
    family = LAGRANGE
    order = FIRST
  []
[]
[Kernels]
  [fe_diffusion]
    type = Diffusion
    variable = log_e
  []
  [rf_imag_diffusion]
    type = Diffusion
    variable = u_rf_imag
  []
[]
[FVKernels]
  [fv_diffusion]
    type = FVDiffusion
    variable = log_O2p
    coeff = 1
  []
[]
[BCs]
  [fe_left]
    type = DirichletBC
    variable = log_e
    boundary = left
    value = 0
  []
  [fe_right]
    type = DirichletBC
    variable = log_e
    boundary = right
    value = 1
  []
  [rf_imag_left]
    type = DirichletBC
    variable = u_rf_imag
    boundary = left
    value = 0
  []
  [rf_imag_right]
    type = DirichletBC
    variable = u_rf_imag
    boundary = right
    value = 1
  []
[]
[FVBCs]
  [fv_left]
    type = FVDirichletBC
    variable = log_O2p
    boundary = left
    value = 0
  []
  [fv_right]
    type = FVDirichletBC
    variable = log_O2p
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
