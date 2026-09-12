[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 1
  xmin = 0.0
  xmax = 1.0
[]

[Variables]
  [n_zero_drop]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [n_cell_drop]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [potential_cell]
    type = MooseVariableFVReal
    initial_condition = 10.0
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en zero_phi zero_flux'
    prop_values = '5.73276 0.0 0.0'
  []
[]

[FVKernels]
  [n_zero_time]
    type = FVTimeKernel
    variable = n_zero_drop
  []
  [n_zero_face_driver]
    type = FVDiffusion
    variable = n_zero_drop
    coeff = zero_flux
  []
  [n_cell_time]
    type = FVTimeKernel
    variable = n_cell_drop
  []
  [n_cell_face_driver]
    type = FVDiffusion
    variable = n_cell_drop
    coeff = zero_flux
  []
  [potential_time]
    type = FVTimeKernel
    variable = potential_cell
  []
[]

[FVBCs]
  [zero_drop_collection]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = n_zero_drop
    boundary = right
    mean_electron_energy = mean_en
    potential = zero_phi
  []
  [cell_drop_collection]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = n_cell_drop
    boundary = right
    mean_electron_energy = mean_en
    potential = potential_cell
  []
  [potential_grounded_face]
    type = FVDirichletBC
    variable = potential_cell
    boundary = right
    value = 0.0
  []
[]

[Postprocessors]
  [n_zero_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_zero_drop
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_cell_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_cell_drop
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_cell_avg]
    type = ElementAverageFunctorPostprocessor
    functor = potential_cell
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  dt = 1.0e-8
  end_time = 1.0e-8
  solve_type = NEWTON
[]

[Outputs]
  csv = true
[]
