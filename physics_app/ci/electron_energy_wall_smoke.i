# Physical electron-energy density smoke.
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
    initial_condition = 5.0e16
  []
  [energy_see]
    type = MooseVariableFVReal
    initial_condition = 5.0e16
  []
[]

[FunctorMaterials]
  [thermal_wall_outward_energy_flux]
    type = ADParsedFunctorMaterial
    property_name = thermal_wall_outward_energy_flux
    functor_names = 'energy_thermal mean_en zero_flux'
    functor_symbols = 'w eps gs'
    expression = '(5.0/6.0)*sqrt(16.0*1.6021766339999999e-19*eps/(3.0*3.141592653589793238462643383279502884*9.1093837138999998e-31))*w-4*gs'
  []
  [see_wall_outward_energy_flux]
    type = ADParsedFunctorMaterial
    property_name = see_wall_outward_energy_flux
    functor_names = 'energy_see mean_en finite_see'
    functor_symbols = 'w eps gs'
    expression = '(5.0/6.0)*sqrt(16.0*1.6021766339999999e-19*eps/(3.0*3.141592653589793238462643383279502884*9.1093837138999998e-31))*w-4*gs'
  []
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
    type = FVFunctorNeumannBC
    variable = energy_thermal
    boundary = right
    functor = thermal_wall_outward_energy_flux
    factor = -1
  []
  [see_wall]
    type = FVFunctorNeumannBC
    variable = energy_see
    boundary = right
    functor = see_wall_outward_energy_flux
    factor = -1
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
