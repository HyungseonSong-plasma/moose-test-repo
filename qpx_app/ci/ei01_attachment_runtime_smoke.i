[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 1
  xmin = 0.0
  xmax = 1.0
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
[]

[FunctorMaterials]
  [ei01_controlled_source]
    type = ADGenericFunctorMaterial
    prop_names = 'ei01_electron_number_source'
    prop_values = '-1.0e16'
  []
[]

[FVKernels]
  [n_e_time]
    type = FVTimeKernel
    variable = n_e
  []
  [ei01_electron_source]
    type = QPXFVElectronReactionSource
    variable = n_e
    number_source = ei01_electron_number_source
    n_ref = 1.0e16
  []
[]

[Postprocessors]
  [n_e_hat_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  dt = 0.1
  end_time = 0.1
  solve_type = NEWTON
[]

[Outputs]
  csv = true
  exodus = false
[]
