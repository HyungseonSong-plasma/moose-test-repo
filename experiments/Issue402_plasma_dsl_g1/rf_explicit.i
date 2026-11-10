[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 8
[]
[Variables]
  [E_real]
    family = LAGRANGE
    order = FIRST
  []
  [E_imag]
    family = LAGRANGE
    order = FIRST
  []
[]
[Materials]
  [rf_coefficients]
    type = GenericConstantMaterial
    prop_names = 'neg_a b'
    prop_values = '-1 0.2'
  []
[]
[Kernels]
  [real_diffusion]
    type = Diffusion
    variable = E_real
  []
  [imag_diffusion]
    type = Diffusion
    variable = E_imag
  []
  [real_reaction]
    type = MatReaction
    variable = E_real
    reaction_rate = neg_a
  []
  [imag_reaction]
    type = MatReaction
    variable = E_imag
    reaction_rate = neg_a
  []
  [real_coupling]
    type = MatCoupledForce
    variable = E_real
    v = E_imag
    coef = 1
    material_properties = b
  []
  [imag_coupling]
    type = MatCoupledForce
    variable = E_imag
    v = E_real
    coef = -1
    material_properties = b
  []
  [imag_source]
    type = BodyForce
    variable = E_imag
    value = 1
  []
[]
[BCs]
  [real_left]
    type = DirichletBC
    variable = E_real
    boundary = left
    value = 0
  []
  [real_right]
    type = DirichletBC
    variable = E_real
    boundary = right
    value = 0
  []
  [imag_left]
    type = DirichletBC
    variable = E_imag
    boundary = left
    value = 0
  []
  [imag_right]
    type = DirichletBC
    variable = E_imag
    boundary = right
    value = 0
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
