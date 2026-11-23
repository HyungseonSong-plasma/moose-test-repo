# Synthetic legacy interface only; no historical replay or science parity
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 4
[]
[Problem]
  solve = false
  kernel_coverage_check = false
[]
[Variables]
  [legacy_mass]
    type = MooseVariableFVReal
    initial_condition = 0
  []
[]
[FunctorMaterials]
  [thermal_fields]
    type = ADGenericFunctorMaterial
    prop_names = 'gas_temperature thermal_D_T'
    prop_values = '600 0.02'
  []
[]
[FVKernels]
  [legacy_thermal]
    type = PhysicsFVThermalDiffusion
    variable = legacy_mass
    temperature = gas_temperature
    thermal_diffusion_coefficient = thermal_D_T
    include_thermal_diffusion = true
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
