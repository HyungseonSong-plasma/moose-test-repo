# Real-QVT RZ Poisson operator probe
#
# Manufactured scalar field:
#   phi_exact(r,z) = r^2 = x^2, with rz_coord_axis = Y
#   laplacian_RZ(phi_exact) = d2/dr2(r^2) + (1/r)d/dr(r^2) = 2 + 2 = 4
#
# Following MOOSE FV diffusion MMS sign convention, FVBodyForce uses -4.
# All physical plasma surfaces receive the exact Dirichlet value; the x=0
# symmetry axis is not a physical boundary and is left to RZ regularity.

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
  [plasma_only]
    type = BlockDeletionGenerator
    input = plasma_focus_ring
    operation = keep
    block = plasma
  []
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [phi_probe]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
[]

[FunctorMaterials]
  [coeff]
    type = ADGenericFunctorMaterial
    prop_names = relative_permittivity
    prop_values = 1.0
    block = plasma
  []
[]

[Functions]
  [exact_phi]
    type = ParsedFunction
    expression = 'x*x'
  []
  [forcing]
    type = ParsedFunction
    expression = '-4.0'
  []
[]

[FVKernels]
  [diffusion]
    type = FVDiffusion
    variable = phi_probe
    coeff = relative_permittivity
    block = plasma
  []
  [source]
    type = FVBodyForce
    variable = phi_probe
    function = forcing
    block = plasma
  []
[]

[FVBCs]
  [exact_physical_boundaries]
    type = FVFunctionDirichletBC
    variable = phi_probe
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    function = exact_phi
  []
[]

[VectorPostprocessors]
  [final_profile]
    type = ElementValueSampler
    variable = phi_probe
    sort_by = id
    execute_on = FINAL
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1.0e-12
  nl_abs_tol = 1.0e-14
  nl_max_its = 50
[]

[Outputs]
  [csv]
    type = CSV
    file_base = rz_operator_probe
    execute_vector_postprocessors_on = FINAL
  []
  [exodus]
    type = Exodus
    file_base = rz_operator_probe
    show = phi_probe
  []
[]
