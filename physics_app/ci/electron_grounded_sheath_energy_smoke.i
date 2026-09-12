[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 1
  xmin = 0.0
  xmax = 1.0
[]

[Variables]
  [energy_zero_drop]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [energy_cell_drop]
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
    prop_names = 'n_e_hat mean_en zero_phi zero_flux'
    prop_values = '1.0 5.73276 0.0 0.0'
  []
[]

[FVKernels]
  [energy_zero_time]
    type = FVTimeKernel
    variable = energy_zero_drop
  []
  [energy_zero_face_driver]
    type = FVDiffusion
    variable = energy_zero_drop
    coeff = zero_flux
  []
  [energy_cell_time]
    type = FVTimeKernel
    variable = energy_cell_drop
  []
  [energy_cell_face_driver]
    type = FVDiffusion
    variable = energy_cell_drop
    coeff = zero_flux
  []
  [potential_time]
    type = FVTimeKernel
    variable = potential_cell
  []
[]

[FVBCs]
  [zero_drop_energy_collection]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = energy_zero_drop
    boundary = right
    electron_density = n_e_hat
    mean_electron_energy = mean_en
    potential = zero_phi
    energy_reference_eV = 5.73276
  []
  [cell_drop_energy_collection]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = energy_cell_drop
    boundary = right
    electron_density = n_e_hat
    mean_electron_energy = mean_en
    potential = potential_cell
    energy_reference_eV = 5.73276
  []
  [potential_grounded_face]
    type = FVDirichletBC
    variable = potential_cell
    boundary = right
    value = 0.0
  []
[]

[Postprocessors]
  [energy_zero_avg]
    type = ElementAverageFunctorPostprocessor
    functor = energy_zero_drop
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [energy_cell_avg]
    type = ElementAverageFunctorPostprocessor
    functor = energy_cell_drop
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
