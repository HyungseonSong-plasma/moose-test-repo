# Log-molar electron-density + Poisson no-drift control.
# Solved electron variable:
#   log_ne = ln[(n_e / N_A) / (1 mol/m^3)]
# phi_0 = 0 V; same 1e-3 density perturbation as the full-drift diagnostic.

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
  [log_ne]
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
  [log_ne_initial]
    type = ParsedFunction
    expression = 'log((1e16*(1.0 + 1e-3*exp(-(((x-0.15)*(x-0.15)+(y-0.15)*(y-0.15))/(0.04*0.04)))))/6.02214076e23)'
  []
[]

[ICs]
  [log_ne_ic]
    type = FunctionIC
    variable = log_ne
    function = log_ne_initial
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'p T_g carrier_one relative_permittivity n_ion_fixed mean_en_fixed'
    prop_values = '1.333223684 300.0 1.0 1.0 1.0e16 5.73276'
    block = plasma
  []

  [electron_molar_density]
    type = ADParsedFunctorMaterial
    property_name = electron_molar_density
    functor_names = 'log_ne'
    functor_symbols = 'u'
    expression = 'exp(u)'
    block = plasma
  []

  [electron_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'electron_molar_density'
    functor_symbols = 'ce'
    expression = '6.02214076e23*ce'
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
    functor_names = 'n_ion_fixed n_e_physical'
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
  [electron_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ne
    block = plasma
  []
  [electron_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ne
    coeff = electron_diffusion
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
  [log_ne_min]
    type = ADElementExtremeFunctorValue
    functor = log_ne
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [log_ne_max]
    type = ADElementExtremeFunctorValue
    functor = log_ne
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_e_min]
    type = ADElementExtremeFunctorValue
    functor = n_e_physical
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_e_max]
    type = ADElementExtremeFunctorValue
    functor = n_e_physical
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
