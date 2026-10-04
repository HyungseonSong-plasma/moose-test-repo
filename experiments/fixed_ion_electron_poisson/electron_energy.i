# Electron + electron-energy sibling.
# State is physical number density n_e [1/m^3] and electron energy density [eV/m^3].
# Chemistry and wall collection are intentionally OFF in this first prototype.

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
  [electron_energy]
    type = MooseVariableFVReal
    block = plasma
  []
[]

[AuxVariables]
  [potential_from_poisson]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
[]

[Functions]
  # This same profile is used as the temporally frozen ion density in poisson.i,
  # so the initial condition is locally quasi-neutral cell by cell.
  [n_e_initial]
    type = ParsedFunction
    expression = '1.0e16*(0.9 + 0.2*x/0.2565)'
  []

  [electron_energy_initial]
    type = ParsedFunction
    expression = '5.73276e16*(1.05 - 0.1*x/0.2565)'
  []
[]

[ICs]
  [n_e_ic]
    type = FunctionIC
    variable = n_e
    function = n_e_initial
    block = plasma
  []

  [electron_energy_ic]
    type = FunctionIC
    variable = electron_energy
    function = electron_energy_initial
    block = plasma
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'p T_g carrier_one'
    prop_values = '1.333223684 300.0 1.0'
    block = plasma
  []

  [mean_energy]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = electron_energy
    electron_density = n_e
    state_form = physical_eV
    block = plasma
  []

  [electron_transport]
    type = PhysicsElectronTransportLookupMaterial
    property_table_file = '../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'
    mean_energy = mean_en_solved
    pressure = p
    gas_temperature = T_g
    bounds_policy = error
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
    type = QPXFVElectrostaticDrift
    variable = n_e
    potential = potential_from_poisson
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []

  [energy_time]
    type = FVTimeKernel
    variable = electron_energy
    block = plasma
  []
  [energy_diffusion]
    type = FVDiffusion
    variable = electron_energy
    coeff = electron_energy_diffusion
    block = plasma
  []
  [energy_drift]
    type = PhysicsFVElectrostaticDrift
    variable = electron_energy
    potential = potential_from_poisson
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    block = plasma
  []
  [energy_joule]
    type = PhysicsFVElectronEnergyJouleHeating
    variable = electron_energy
    electron_density = n_e
    potential = potential_from_poisson
    mobility = electron_mobility
    diffusion = electron_diffusion
    state_form = physical_eV
    block = plasma
  []
[]

[Postprocessors]
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
  [n_e_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_min]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_max]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_from_poisson
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_from_poisson
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON

  dt = 5.0e-11
  dtmin = 5.0e-11
  dtmax = 5.0e-11
  num_steps = 20
  end_time = 1.0e-9
  timestep_tolerance = 1.0e-18

  nl_rel_tol = 1.0e-9
  nl_abs_tol = 1.0e-12
  nl_max_its = 50
  automatic_scaling = true

  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  exodus = true
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
