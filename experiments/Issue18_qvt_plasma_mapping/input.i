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
# ==============================================================================
# R18 EVR #1 qvt.msh candidate
# The fixed user-supplied mesh.i is prepended byte-for-byte by prepare.py.
# ==============================================================================

[Variables]
  [dummy]
    initial_condition = 0
  []
[]

[Kernels]
  [dummy_reaction]
    type = Reaction
    variable = dummy
  []
[]

[BCs]
  [plasma_generated_boundaries]
    type = DirichletBC
    variable = dummy
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    value = 0
  []
[]

[FunctorMaterials]
  [r18_state]
    type = ADGenericFunctorMaterial
    prop_names = 'T_g p_abs T_e n_e_A n_e_B w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    prop_values = '600 13.332 20000 1e16 1e18 0.70 0.05 0.01 0.10 0.01 0.01 0.12'
    block = plasma
  []

  [r18_transport_A]
    type = QPXThermalDiffusionMaterial
    temperature = T_g
    pressure = p_abs
    electron_temperature = T_e
    electron_number_density = n_e_A
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'Dmix_A_O2 Dmix_A_O2s Dmix_A_O2p Dmix_A_O Dmix_A_Om Dmix_A_Op Dmix_A_Os'
    D_T_names = 'DT_A_O2 DT_A_O2s DT_A_O2p DT_A_O DT_A_Om DT_A_Op DT_A_Os'
    kT_names = 'kT_A_O2 kT_A_O2s kT_A_O2p kT_A_O kT_A_Om kT_A_Op kT_A_Os'
    block = plasma
  []

  [r18_transport_B]
    type = QPXThermalDiffusionMaterial
    temperature = T_g
    pressure = p_abs
    electron_temperature = T_e
    electron_number_density = n_e_B
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'Dmix_B_O2 Dmix_B_O2s Dmix_B_O2p Dmix_B_O Dmix_B_Om Dmix_B_Op Dmix_B_Os'
    D_T_names = 'DT_B_O2 DT_B_O2s DT_B_O2p DT_B_O DT_B_Om DT_B_Op DT_B_Os'
    kT_names = 'kT_B_O2 kT_B_O2s kT_B_O2p kT_B_O kT_B_Om kT_B_Op kT_B_Os'
    block = plasma
  []
[]

[Postprocessors]
  [Dmix_A_O2]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_A_O2s]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_O2s
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_A_O2p]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_O2p
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_A_O]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_O
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_A_Om]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_Om
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_A_Op]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_Op
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_A_Os]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_Os
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_B_O2]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_B_O2s]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_O2s
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_B_O2p]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_O2p
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_B_O]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_O
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_B_Om]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_Om
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_B_Op]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_Op
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_B_Os]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_Os
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [dummy_plasma_avg]
    type = ElementAverageValue
    variable = dummy
    block = plasma
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_abs_tol = 1e-12
  nl_rel_tol = 1e-12
  nl_max_its = 10
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
