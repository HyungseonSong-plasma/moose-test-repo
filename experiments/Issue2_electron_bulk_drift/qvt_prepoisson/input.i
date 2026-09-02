[Mesh]
  coord_type = RZ
  rz_coord_axis = Y

  [main]
    type = FileMeshGenerator
    file = 'qvt.msh'
  []
  [inlet]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = port
    new_boundary = inlet
    input = main
  []
  [outlet]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = bottom
    new_boundary = outlet
    input = inlet
  []
  [plasma_electrode]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = electrode
    new_boundary = plasma_electrode
    input = outlet
  []
  [plasma_metal]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = metal
    new_boundary = plasma_metal
    input = plasma_electrode
  []
  [plasma_right]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = right
    new_boundary = plasma_right
    input = plasma_metal
  []
  [plasma_cover]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = cover
    new_boundary = plasma_cover
    input = plasma_right
  []
  [plasma_wafer]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = wafer
    new_boundary = plasma_wafer
    input = plasma_cover
  []
  [plasma_focus_ring]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = focus_ring
    new_boundary = plasma_focus_ring
    input = plasma_wafer
  []
  [cover_vacuum]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = cover
    paired_block = vacuum
    new_boundary = cover_vacuum
    input = plasma_focus_ring
  []
  [cover_coil]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = cover
    paired_block = 'coil1 coil2 coil3'
    new_boundary = cover_coil
    input = cover_vacuum
  []
  [vacuum_coil]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = vacuum
    paired_block = 'coil1 coil2 coil3'
    new_boundary = vacuum_coil
    input = cover_coil
  []
  [outer_cover]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = cover
    paired_block = 'port top'
    new_boundary = outer_cover
    input = vacuum_coil
  []
  [metal_focus_ring]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = focus_ring
    paired_block = metal
    new_boundary = metal_focus_ring
    input = outer_cover
  []
  [outer_vacuum]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = vacuum
    paired_block = top
    new_boundary = outer_vacuum
    input = metal_focus_ring
  []
  [electrode_focus_ring]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = electrode
    paired_block = focus_ring
    new_boundary = electrode_focus_ring
    input = outer_vacuum
  []
  [electrode_wafer]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = electrode
    paired_block = wafer
    new_boundary = electrode_wafer
    input = electrode_focus_ring
  []
  [bottom_metal]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = bottom
    paired_block = metal
    new_boundary = bottom_metal
    input = electrode_wafer
  []
  [bottom_focus_ring]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = bottom
    paired_block = focus_ring
    new_boundary = bottom_focus_ring
    input = bottom_metal
  []
  [bottom_electrode]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = bottom
    paired_block = electrode
    new_boundary = bottom_electrode
    input = bottom_focus_ring
  []
[]

[Materials]
  [vacuum]
    type = BaseMaterial
    material_name = vacuum
    relative_permittivity = 1
    conductivity = 1e-8
    block = vacuum
  []
  [outer]
    type = BaseMaterial
    material_name = outer
    relative_permittivity = 1
    conductivity = 0
    block = 'top right bottom'
  []
  [cover]
    type = BaseMaterial
    material_name = cover
    relative_permittivity = 3.6
    conductivity = 1e-6
    block = cover
  []
  [electrode]
    type = BaseMaterial
    material_name = electrode
    relative_permittivity = 1
    conductivity = 0
    block = electrode
  []
  [wafer]
    type = BaseMaterial
    material_name = wafer
    relative_permittivity = 12.5
    conductivity = 1e-2
    block = wafer
  []
  [focus_ring]
    type = BaseMaterial
    material_name = focus_ring
    relative_permittivity = 8
    conductivity = 1e-6
    block = focus_ring
  []
  [plasma]
    type = BaseMaterial
    material_name = plasma
    relative_permittivity = 1
    conductivity = 0
  []
[]

# R2 EVR1 T6: real-qvt pre-Poisson electron drift-diffusion
[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1e+16
    block = plasma
  []
[]

[Functions]
  [phi_prescribed]
    type = ParsedFunction
    expression = '-0.01*x'
  []
[]

[FunctorMaterials]
  [electron_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en p_abs T_g carrier_one'
    prop_values = '5.73276 1.33322 600.0 1.0'
    block = plasma
  []
  [electron_transport]
    type = QPXElectronTransportLookupMaterial
    property_table_file = electron_moments.txt
    mean_energy = mean_en
    pressure = p_abs
    gas_temperature = T_g
    bounds_policy = error
    block = plasma
  []
[]

[FVKernels]
  [time]
    type = FVTimeKernel
    variable = n_e
    block = plasma
  []
  [diffusion]
    type = FVDiffusion
    variable = n_e
    coeff = electron_diffusion
    block = plasma
  []
  [drift]
    type = QPXFVElectrostaticDrift
    variable = n_e
    potential = phi_prescribed
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []
[]

[Postprocessors]
  [n_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
    block = plasma
  []
  [n_min]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = min
    block = plasma
  []
  [n_max]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = max
    block = plasma
  []
  [inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e
    block = plasma
  []
  [domain_volume]
    type = ADElementIntegralFunctorPostprocessor
    functor = carrier_one
    block = plasma
  []
  [neutral_number_density_avg]
    type = ElementAverageFunctorPostprocessor
    functor = neutral_number_density
    block = plasma
  []
  [electron_mobility_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mobility
    block = plasma
  []
  [electron_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_diffusion
    block = plasma
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 1e-8
  end_time = 2e-8
  nl_rel_tol = 1e-8
  nl_max_its = 30
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = true
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
