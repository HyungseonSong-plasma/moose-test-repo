# 2d-icp-electron-diffusion-experiment
#
# Reusable minimal 2-D ICP electron-particle diffusion baseline.
#
# Solved physics:
#   d(c_e)/dt - div(D_e grad(c_e)) = 0
#
# Electron energy is NOT solved.  A fixed mean electron energy is converted to
# a derived electron energy density so PhysicsElectronClosureMaterial still
# obtains D_e from the production electron_moments.txt table.
#
# Electrostatic drift, Poisson, electron reactions, and electron-energy
# transport are intentionally absent.
#
# Wall loss uses PhysicsFVElectronGroundedSheathCollectionBC with potential=0.
# Therefore the sheath suppression factor is exactly one and the BC reduces to
# the thermal quarter-Maxwellian collection law at the fixed mean energy.

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
  [log_e]
    type = MooseVariableFVReal
    # n_e0 = 1.0e16 1/m^3
    # c_e0 = n_e0/N_A = 1.6605390671738467e-08 mol/m^3
    initial_condition = -17.913538455038942
    block = plasma
  []
[]

[AuxVariables]
  [electron_density_out]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
    block = plasma
  []
  [mean_energy_out]
    type = MooseVariableFVReal
    initial_condition = 5.73276
    block = plasma
  []
  [diffusion_out]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'gas_pressure_Pa gas_temperature_K fixed_mean_energy_eV zero_phi'
    prop_values = '1.333223684 300.0 5.73276 0.0'
    block = plasma
  []

  [electron_molar_density]
    type = ADParsedFunctorMaterial
    property_name = c_e_molar
    functor_names = 'log_e'
    functor_symbols = 'loge'
    expression = 'exp(loge)'
    block = plasma
  []

  [electron_number_density]
    type = ADParsedFunctorMaterial
    property_name = electron_density_m3
    functor_names = 'c_e_molar'
    functor_symbols = 'ce'
    expression = '6.02214076e23*ce'
    block = plasma
  []

  [fixed_electron_energy_density]
    type = ADParsedFunctorMaterial
    property_name = electron_energy_density_eV_m3
    functor_names = 'electron_density_m3 fixed_mean_energy_eV'
    functor_symbols = 'ne mean_ev'
    expression = 'ne*mean_ev'
    block = plasma
  []

  [electron_transport]
    type = PhysicsElectronClosureMaterial
    state_form = physical_eV
    electron_number_density = electron_density_m3
    electron_energy_density = electron_energy_density_eV_m3
    gas_pressure = gas_pressure_Pa
    gas_temperature = gas_temperature_K
    transport_table_file = electron_moments.txt
    lookup_bounds_policy = error
    electron_mean_energy_output = mean_energy_from_table_state
    electron_temperature_output = electron_temperature_K
    neutral_number_density_output = neutral_number_density_m3
    electron_reduced_mobility_output = electron_reduced_mobility
    electron_reduced_diffusion_output = electron_reduced_diffusion
    electron_mobility_output = electron_mobility
    electron_diffusion_output = electron_diffusion
    electron_energy_mobility_output = electron_energy_mobility
    electron_energy_diffusion_output = electron_energy_diffusion
    block = plasma
  []
[]

[FVKernels]
  [electron_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_e
    block = plasma
  []

  [electron_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_e
    coeff = electron_diffusion
    coeff_interp_method = harmonic
    block = plasma
  []
[]

[FVBCs]
  [electron_thermal_wall_loss]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = log_e
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    mean_electron_energy = mean_energy_from_table_state
    potential = zero_phi
    log_molar_state = true
  []
[]

[AuxKernels]
  [electron_density_copy]
    type = FunctorAux
    variable = electron_density_out
    functor = electron_density_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_copy]
    type = FunctorAux
    variable = mean_energy_out
    functor = mean_energy_from_table_state
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [diffusion_copy]
    type = FunctorAux
    variable = diffusion_out
    functor = electron_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Postprocessors]
  [electron_inventory_mol]
    type = ADElementIntegralFunctorPostprocessor
    functor = c_e_molar
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_density_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_density_m3
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_density_min]
    type = ADElementExtremeFunctorValue
    functor = electron_density_m3
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_density_max]
    type = ADElementExtremeFunctorValue
    functor = electron_density_m3
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_avg_eV]
    type = ElementAverageFunctorPostprocessor
    functor = mean_energy_from_table_state
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_diffusion
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_wall_particle_rate]
    type = SideFVFluxBCIntegral
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    fvbcs = 'electron_thermal_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[VectorPostprocessors]
  [final_profile]
    type = ElementValueSampler
    variable = 'electron_density_out mean_energy_out diffusion_out'
    sort_by = id
    execute_on = 'FINAL'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 1.0e-9
  dtmin = 1.0e-9
  dtmax = 1.0e-9
  end_time = 4.0e-9
  num_steps = 4
  timestep_tolerance = 1.0e-18
  nl_rel_tol = 1.0e-9
  nl_abs_tol = 1.0e-13
  nl_max_its = 80
  automatic_scaling = true
  compute_scaling_once = true
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  [csv]
    type = CSV
    file_base = electron_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
    execute_vector_postprocessors_on = 'FINAL'
  []
  [exodus]
    type = Exodus
    file_base = electron_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
