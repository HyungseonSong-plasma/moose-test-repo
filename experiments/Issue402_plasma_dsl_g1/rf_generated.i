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
[Physics]
  [Plasmas]
    [Maxwell]
      field_real = E_real
      field_imag = E_imag
      frequency_hz = 13560000
      reaction_material = neg_a
      coupling_material = b
      imaginary_source = 1
      ground_boundaries = 'left right'
    []
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
