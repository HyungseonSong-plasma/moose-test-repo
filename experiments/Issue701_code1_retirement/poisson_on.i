# code1 R2 exploratory bounded native characterization, NOT scientific retirement.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 4
  xmin = 0.0
  xmax = 1.0
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [potential_plasma]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[AuxVariables]
  [phi_anchor_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'relative_permittivity electron_response_beta source_constant'
    prop_values = '1.0 160.0 1.0'
  []
[]

[FVKernels]
  [phi_diffusion]
    type = FVDiffusion
    variable = potential_plasma
    coeff = relative_permittivity
  []
  [phi_charge]
    type = FVCoupledForce
    variable = potential_plasma
    v = source_constant
    coef = 1.0
  []
  [electron_response_banded_correction]
    type = FVElectronResponseBandedCorrection
    variable = potential_plasma
    anchor = phi_anchor_frozen
    beta = electron_response_beta
    matrix = '1 -1 0 0 -1 2 -1 0 0 -1 2 -1 0 0 -1 1'
    n_cells = 4
    bandwidth = 1
    xmin = 0.0
    dx = 0.25
    ghost_layers = 2
  []
[]

[FVBCs]
  [left_zero]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = left
    value = 0.0
  []
  [right_zero]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = right
    value = 0.0
  []
[]

[Postprocessors]
  [phi_avg]
    type = ElementAverageFunctorPostprocessor
    functor = potential_plasma
    execute_on = 'INITIAL FINAL'
  []
  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = min
    execute_on = 'INITIAL FINAL'
  []
  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = max
    execute_on = 'INITIAL FINAL'
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1.0e-10
  nl_abs_tol = 1.0e-12
  nl_max_its = 40
  automatic_scaling = true
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  csv = true
  exodus = true
[]
