# Real-QVT RZ spatial-source coupling probe
#
# Manufactured solution on the actual ICP plasma mesh:
#   phi_exact(r,z) = r^2 z^2 = x^2 y^2, with rz_coord_axis = Y
#   laplacian_RZ(phi_exact) = 4 z^2 + 2 r^2
#
# The production Poisson sign convention is
#   -laplacian(phi) = source,
# so the manufactured source supplied through the same
# ADParsedFunctorMaterial -> FVCoupledForce path is
#   source = -(4 y^2 + 2 x^2).
#
# All physical plasma surfaces receive the exact Dirichlet value. The x=0
# symmetry axis is not a physical boundary and remains governed by RZ
# regularity/natural semantics.

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

[AuxVariables]
  [source_out]
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

  [manufactured_source]
    type = ADParsedFunctorMaterial
    property_name = manufactured_poisson_source
    expression = '-(4.0*y*y + 2.0*x*x)'
    block = plasma
  []
[]

[Functions]
  [exact_phi]
    type = ParsedFunction
    expression = 'x*x*y*y'
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
    type = FVCoupledForce
    variable = phi_probe
    v = manufactured_poisson_source
    coef = 1.0
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

[AuxKernels]
  [source_copy]
    type = FunctorAux
    variable = source_out
    functor = manufactured_poisson_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[VectorPostprocessors]
  [final_profile]
    type = ElementValueSampler
    variable = 'phi_probe source_out'
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
    file_base = rz_spatial_source_probe
    execute_vector_postprocessors_on = FINAL
  []
  [exodus]
    type = Exodus
    file_base = rz_spatial_source_probe
    show = 'phi_probe source_out'
  []
[]
