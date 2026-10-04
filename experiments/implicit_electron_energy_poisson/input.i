# Fully implicit physical-time electron + electron-energy + Poisson prototype.
# n_e, electron_energy, and potential are solved in one nonlinear system.
# Fixed ion density is a frozen heavy-state surrogate for this matrix test.

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
    initial_condition = 1.0e16
    block = plasma
  []
  [electron_energy]
    type = MooseVariableFVReal
    initial_condition = 5.73276e16
    block = plasma
  []
  [potential]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
[]

[AuxVariables]
  [mean_energy_aux]
    type = MooseVariableFVReal
    block = plasma
  []
  [charge_density_aux]
    type = MooseVariableFVReal
    block = plasma
  []
  [poisson_source_aux]
    type = MooseVariableFVReal
    block = plasma
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'p T_g carrier_one relative_permittivity n_ion_fixed'
    prop_values = '1.333223684 300.0 1.0 1.0 1.0e16'
    block = plasma
  []

  [mean_energy]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = electron_energy
    electron_density = n_e
    state_form = physical_eV
    energy_reference_eV = 1.0
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

  [charge_number_density]
    type = ADParsedFunctorMaterial
    property_name = charge_number_density
    functor_names = 'n_ion_fixed n_e'
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
    potential = potential
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
    potential = potential
    mobility = electron_mobility
    diffusion = electron_diffusion
    state_form = physical_eV
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
  [electron_sheath_loss]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = n_e
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    mean_electron_energy = mean_en_solved
    potential = potential
    log_molar_state = false
  []

  [electron_energy_sheath_loss]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = electron_energy
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    electron_density = n_e
    mean_electron_energy = mean_en_solved
    potential = potential
    physical_eV_state = true
  []

  [grounded_potential]
    type = FVDirichletBC
    variable = potential
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    value = 0.0
  []
[]

[AuxKernels]
  [sample_mean_energy]
    type = FunctorAux
    variable = mean_energy_aux
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sample_charge_density]
    type = FunctorAux
    variable = charge_density_aux
    functor = charge_density_C_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sample_poisson_source]
    type = FunctorAux
    variable = poisson_source_aux
    functor = poisson_charge_source
    execute_on = 'INITIAL TIMESTEP_END'
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
  [n_e_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [energy_min]
    type = ADElementExtremeFunctorValue
    functor = electron_energy
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [energy_max]
    type = ADElementExtremeFunctorValue
    functor = electron_energy
    value_type = max
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
  num_steps = 1
  end_time = 1.0e-9
  timestep_tolerance = 1.0e-18

  nl_rel_tol = 1.0e-8
  nl_abs_tol = 1.0e-12
  nl_max_its = 20
  automatic_scaling = true

  petsc_options = '-snes_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type -snes_linesearch_type'
  petsc_options_value = 'preonly lu NONZERO bt'
[]

[Outputs]
  exodus = true
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
