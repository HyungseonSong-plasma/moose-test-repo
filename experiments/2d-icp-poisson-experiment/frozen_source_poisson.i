# Standalone Poisson replay using the actual source saved by a canonical run.
#
# The workflow stages canonical_source.e from the same exact-head canonical
# transient run. This input contains no electron or energy equations. It reads
# poisson_source_out from the Exodus file, copies it into an elemental auxiliary
# variable, and solves only the RZ Poisson equation with the same physical BCs.

[Mesh]
  coord_type = RZ
  rz_coord_axis = Y
  parallel_type = replicated

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
  # x=0 is the RZ symmetry axis, not a physical boundary.
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
  [phi]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
[]

[AuxVariables]
  [frozen_poisson_source]
    family = MONOMIAL
    order = CONSTANT
    block = plasma
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = relative_permittivity
    prop_values = 1.0
    block = plasma
  []
[]

[UserObjects]
  [canonical_solution]
    type = SolutionUserObject
    mesh = canonical_source.e
    system_variables = poisson_source_out
    execute_on = INITIAL
  []
[]

[AuxKernels]
  [load_frozen_source]
    type = SolutionAux
    variable = frozen_poisson_source
    solution = canonical_solution
    from_variable = poisson_source_out
    direct = true
    execute_on = INITIAL
  []
[]

[FVKernels]
  [phi_diffusion]
    type = FVDiffusion
    variable = phi
    coeff = relative_permittivity
    block = plasma
  []

  [phi_charge_source]
    type = FVCoupledForce
    variable = phi
    v = frozen_poisson_source
    coef = 1.0
    block = plasma
  []
[]

[FVBCs]
  [phi_grounded_walls]
    type = FVDirichletBC
    variable = phi
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    value = 0.0
  []
[]

[VectorPostprocessors]
  [final_profile]
    type = ElementValueSampler
    variable = 'frozen_poisson_source phi'
    sort_by = id
    execute_on = FINAL
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1.0e-12
  nl_abs_tol = 1.0e-12
  nl_max_its = 50
[]

[Outputs]
  [csv]
    type = CSV
    file_base = frozen_source_poisson
    execute_vector_postprocessors_on = FINAL
  []
  [exodus]
    type = Exodus
    file_base = frozen_source_poisson
    show = 'frozen_poisson_source phi'
  []
[]
