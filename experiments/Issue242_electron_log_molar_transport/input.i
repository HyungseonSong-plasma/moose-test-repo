# Issue 242 T0: electron bulk-transport representation discriminator.
# Control solves physical n_e [1/m^3]. Candidate solves log_e with
# c_e = exp(log_e) [mol/m^3] and n_e,candidate = N_A c_e.

[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 80
  xmin = 0
  xmax = 1
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
  []
  [log_e]
    type = MooseVariableFVReal
  []
[]

[Functions]
  [n_ic]
    type = ParsedFunction
    expression = '1e16*(1.0 + 0.2*cos(6.283185307179586*x))'
  []
  [log_e_ic]
    type = ParsedFunction
    expression = 'log((1e16*(1.0 + 0.2*cos(6.283185307179586*x)))/6.02214076e23)'
  []
  [phi_prescribed]
    type = ParsedFunction
    expression = '-0.5*x'
  []
[]

[ICs]
  [n_e_ic]
    type = FunctionIC
    variable = n_e
    function = n_ic
  []
  [log_e_ic]
    type = FunctionIC
    variable = log_e
    function = log_e_ic
  []
[]

[FunctorMaterials]
  [transport_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'electron_diffusion electron_mobility carrier_one'
    prop_values = '0.02 0.1 1.0'
  []

  [candidate_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_candidate
    functor_names = 'log_e'
    functor_symbols = 'le'
    expression = '6.02214076e23*exp(le)'
  []

  [density_error]
    type = ADParsedFunctorMaterial
    property_name = n_e_error
    functor_names = 'n_e n_e_candidate'
    functor_symbols = 'ne nec'
    expression = 'ne-nec'
  []

  [density_error_sq]
    type = ADParsedFunctorMaterial
    property_name = n_e_error_sq
    functor_names = 'n_e_error'
    functor_symbols = 'err'
    expression = 'err*err'
  []

  [density_error_abs]
    type = ADParsedFunctorMaterial
    property_name = n_e_error_abs
    functor_names = 'n_e_error'
    functor_symbols = 'err'
    expression = 'sqrt(err*err)'
  []

  [control_sq]
    type = ADParsedFunctorMaterial
    property_name = n_e_control_sq
    functor_names = 'n_e'
    functor_symbols = 'ne'
    expression = 'ne*ne'
  []
[]

[FVKernels]
  [control_time]
    type = FVTimeKernel
    variable = n_e
  []
  [control_diffusion]
    type = FVDiffusion
    variable = n_e
    coeff = electron_diffusion
  []
  [control_drift]
    type = PhysicsFVElectrostaticDrift
    variable = n_e
    potential = phi_prescribed
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
  []

  [candidate_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_e
  []
  [candidate_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_e
    coeff = electron_diffusion
  []
  [candidate_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_e
    potential = phi_prescribed
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
  []
[]

[Postprocessors]
  [control_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [candidate_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e_candidate
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [control_min]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [candidate_min]
    type = ADElementExtremeFunctorValue
    functor = n_e_candidate
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [control_max]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [control_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [candidate_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e_candidate
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [error_l2_sq]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e_error_sq
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [control_l2_sq]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e_control_sq
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [error_linf]
    type = ADElementExtremeFunctorValue
    functor = n_e_error_abs
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 0.01
  end_time = 0.05
  nl_rel_tol = 1e-11
  nl_abs_tol = 1e-13
  nl_max_its = 40
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
