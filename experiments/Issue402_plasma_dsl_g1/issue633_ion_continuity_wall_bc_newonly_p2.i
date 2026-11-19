# Issue #633 C2 combined 3-ion Native-ion-free P2 (synthetic geometry).
# 3 x time/diffusion/drift/source FV kernels, 3 ion wall materials,
# 3 general + 9 dielectric FV BCs, and 3 new surface-current functors.
# No Poisson/RF/neutral solve, no Native ion kernel/BC, no timesteps or P3.
# Eight names are synthetic S6 *characterization*, not generic C++ geometry.
# ParsedGenerateSideset combinatorial_geometry uses FunctionParser '&', not C-style '&&'.
[Mesh]
  [base]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 2
    ny = 2
    xmin = 0
    xmax = 1
    ymin = 0
    ymax = 1
  []
  [plasma_block]
    type = SubdomainBoundingBoxGenerator
    input = base
    bottom_left = '-1 -1 -1'
    top_right = '2 2 1'
    block_id = 1
    block_name = plasma
  []
  [inlet_side]
    type = ParsedGenerateSideset
    input = plasma_block
    combinatorial_geometry = 'abs(x) < 1e-10 & y < 0.5'
    normal = '-1 0 0'
    new_sideset_name = inlet
  []
  [outlet_side]
    type = ParsedGenerateSideset
    input = inlet_side
    combinatorial_geometry = 'abs(x) < 1e-10 & y > 0.5'
    normal = '-1 0 0'
    new_sideset_name = outlet
  []
  [plasma_electrode_side]
    type = ParsedGenerateSideset
    input = outlet_side
    combinatorial_geometry = 'abs(x - 1) < 1e-10 & y < 0.5'
    normal = '1 0 0'
    new_sideset_name = plasma_electrode
  []
  [plasma_metal_side]
    type = ParsedGenerateSideset
    input = plasma_electrode_side
    combinatorial_geometry = 'abs(x - 1) < 1e-10 & y > 0.5'
    normal = '1 0 0'
    new_sideset_name = plasma_metal
  []
  [plasma_right_side]
    type = ParsedGenerateSideset
    input = plasma_metal_side
    combinatorial_geometry = 'abs(y - 1) < 1e-10 & x < 0.5'
    normal = '0 1 0'
    new_sideset_name = plasma_right
  []
  [plasma_cover_side]
    type = ParsedGenerateSideset
    input = plasma_right_side
    combinatorial_geometry = 'abs(y - 1) < 1e-10 & x > 0.5'
    normal = '0 1 0'
    new_sideset_name = plasma_cover
  []
  [plasma_wafer_side]
    type = ParsedGenerateSideset
    input = plasma_cover_side
    combinatorial_geometry = 'abs(y) < 1e-10 & x < 0.5'
    normal = '0 -1 0'
    new_sideset_name = plasma_wafer
  []
  [plasma_focus_ring_side]
    type = ParsedGenerateSideset
    input = plasma_wafer_side
    combinatorial_geometry = 'abs(y) < 1e-10 & x > 0.5'
    normal = '0 -1 0'
    new_sideset_name = plasma_focus_ring
  []
[]

[Problem]
  solve = false
  kernel_coverage_check = false
[]
[Variables]
  [potential]
    family = LAGRANGE
    order = FIRST
    initial_condition = 0
    block = plasma
  []
  [pressure]
    type = MooseVariableFVReal
    block = plasma
  []
[]
[FunctorMaterials]
  [synthetic_progress_carrier_and_electron_wall]
    type = ADGenericFunctorMaterial
    prop_names = 'R_EI415 R_EI401 R_EI417 carrier_one electron_wall_number_flux'
    prop_values = '1 1 1 1 1'
    block = plasma
  []
[]
[Physics]
  [Plasmas]
    files = 'issue633_ion_continuity_newonly_p2.json ../../physics_app/ci/issue633_c2_wall_3ion_overlay.json'
    pressure = 1.333223684
    temperature = 300
    [Transport]
      [Chemistry]
        block = plasma
      []
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fvm_species = 'O2p Om Op'
          fem_potential = potential
          # Deliberately OMIT migration_smoothing_width: default 0 = hard max.
        []
      []
    []
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
