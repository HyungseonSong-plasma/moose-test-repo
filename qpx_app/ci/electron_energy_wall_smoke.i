[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 1
  xmin = 0.0
  xmax = 1.0
[]

[Variables]
  [energy_thermal]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [energy_see]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
[]

[FunctorMaterials]
  [wall_contract]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en zero_flux finite_see'
    prop_values = '5.0 0.0 100000.0'
  []
[]

[FVKernels]
  [thermal_time]
    type = FVTimeKernel
    variable = energy_thermal
  []
  [thermal_face_driver]
    type = FVDiffusion
    variable = energy_thermal
    coeff = zero_flux
  []
  [see_time]
    type = FVTimeKernel
    variable = energy_see
  []
  [see_face_driver]
    type = FVDiffusion
    variable = energy_see
    coeff = zero_flux
  []
[]

[FVBCs]
  [thermal_wall]
    type = PhysicsFVElectronEnergyWallFluxBC
    variable = energy_thermal
    boundary = right
    electron_energy_density = energy_thermal
    mean_electron_energy = mean_en
    see_number_flux = zero_flux
    energy_reference_eV = 5.0
  []
  [see_wall]
    type = PhysicsFVElectronEnergyWallFluxBC
    variable = energy_see
    boundary = right
    electron_energy_density = energy_see
    mean_electron_energy = mean_en
    see_number_flux = finite_see
    energy_reference_eV = 5.0
  []
[]

[Postprocessors]
  [energy_thermal_avg]
    type = ElementAverageFunctorPostprocessor
    functor = energy_thermal
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [energy_see_avg]
    type = ElementAverageFunctorPostprocessor
    functor = energy_see
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
