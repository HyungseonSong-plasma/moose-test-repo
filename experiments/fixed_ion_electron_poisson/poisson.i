# Poisson sibling with temporally frozen positive ion density.
# Uniform fixed ion density equals the initial uniform electron density, so the
# prototype starts exactly quasi-neutral. Only n_e evolves and is transferred.

[Mesh]
  coord_type = RZ
  rz_coord_axis = Y

  [main]
    type = FileMeshGenerator
    file = '../Issue91_real_qvt_r3/r3_e0/qvt.msh'
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
  [potential]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
[]

[AuxVariables]
  [n_e_from_electron]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
    block = plasma
  []
  [n_ion_fixed]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
    block = plasma
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'relative_permittivity'
    prop_values = '1.0'
    block = plasma
  []

  [charge_number_density]
    type = ADParsedFunctorMaterial
    property_name = charge_number_density
    functor_names = 'n_ion_fixed n_e_from_electron'
    functor_symbols = 'ni ne'
    expression = 'ni-ne'
    block = plasma
  []

  [charge_density]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.602176634e-19*nq'
    block = plasma
  []

  [poisson_source]
    type = ADParsedFunctorMaterial
    property_name = poisson_charge_source
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.8095128179727827e-08*nq'
    block = plasma
  []
[]

[FVKernels]
  [phi_diffusion]
    type = FVDiffusion
    variable = potential
    coeff = relative_permittivity
    block = plasma
  []

  [phi_charge_source]
    type = FVCoupledForce
    variable = potential
    v = poisson_charge_source
    coef = 1.0
    block = plasma
  []
[]

[FVBCs]
  [grounded_boundaries]
    type = FVDirichletBC
    variable = potential
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    value = 0.0
  []
[]

[Postprocessors]
  [ion_min]
    type = ADElementExtremeFunctorValue
    functor = n_ion_fixed
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ion_max]
    type = ADElementExtremeFunctorValue
    functor = n_ion_fixed
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_min]
    type = ADElementExtremeFunctorValue
    functor = n_e_from_electron
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_max]
    type = ADElementExtremeFunctorValue
    functor = n_e_from_electron
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_min]
    type = ADElementExtremeFunctorValue
    functor = charge_density_C_m3
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_max]
    type = ADElementExtremeFunctorValue
    functor = charge_density_C_m3
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density_C_m3
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON

  dt = 1.0e-9
  dtmin = 1.0e-9
  dtmax = 1.0e-9
  num_steps = 10
  end_time = 1.0e-8
  timestep_tolerance = 1.0e-18

  nl_rel_tol = 1.0e-10
  nl_abs_tol = 1.0e-12
  nl_max_its = 20
  automatic_scaling = true

  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  exodus = true
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
