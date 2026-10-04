# Electron-Poisson nonlinear isolation experiment: fully implicit density in drift.
# phi_0 = 0 V. The upwind selector is frozen from E^n, while both n_e and grad(phi)
# remain current nonlinear unknowns in the drift flux.

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
  [n_e]
    type = MooseVariableFVReal
    block = plasma
  []
  [potential]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
[]

[Functions]
  [n_e_initial]
    type = ParsedFunction
    expression = '1e16*(1.0 + 1e-3*exp(-(((x-0.15)*(x-0.15)+(y-0.15)*(y-0.15))/(0.04*0.04))))'
  []
[]

[ICs]
  [n_e_ic]
    type = FunctionIC
    variable = n_e
    function = n_e_initial
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'p T_g carrier_one relative_permittivity n_ion_fixed mean_en_fixed'
    prop_values = '1.333223684 300.0 1.0 1.0 1.0e16 5.73276'
    block = plasma
  []
  [electron_transport]
    type = PhysicsElectronTransportLookupMaterial
    property_table_file = '../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'
    mean_energy = mean_en_fixed
    pressure = p
    gas_temperature = T_g
    bounds_policy = error
    block = plasma
  []
  [charge_number_density]
    type = ADParsedFunctorMaterial
    property_name = charge_number_density
    functor_names = 'n_ion_fixed n_e'
    functor_symbols = 'ni ne'
    expression = 'ni-ne'
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
  [electron_time]
    type = FVTimeKernel
    variable = n_e
    block = plasma
  []
  [electron_diffusion]
    type = FVDiffusion
    variable = n_e
    coeff = electron_diffusion
    block = plasma
  []
  [electron_drift]
    type = PhysicsFVElectrostaticDrift
    variable = n_e
    potential = potential
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    freeze_upwind_direction_to_old_potential = true
    lag_advected_variable_to_old_time = false
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []
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
  [grounded_potential]
    type = FVDirichletBC
    variable = potential
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    value = 0.0
  []
[]

[Postprocessors]
  [num_dofs]
    type = NumDOFs
    system = NL
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [nonlinear_iterations]
    type = NumNonlinearIterations
    execute_on = TIMESTEP_END
  []
  [linear_iterations]
    type = NumLinearIterations
    execute_on = TIMESTEP_END
  []
  [residual_evaluations]
    type = NumResidualEvaluations
    execute_on = TIMESTEP_END
  []
  [n_e_min]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_e_max]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = max
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
  num_steps = 1
  end_time = 1.0e-9
  timestep_tolerance = 1.0e-18
  nl_rel_tol = 1.0e-10
  nl_abs_tol = 1.0e-12
  nl_max_its = 20
  automatic_scaling = true
  petsc_options = '-snes_converged_reason -snes_monitor -snes_linesearch_monitor -ksp_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type -snes_linesearch_type'
  petsc_options_value = 'preonly lu NONZERO bt'
[]

[Outputs]
  exodus = true
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
