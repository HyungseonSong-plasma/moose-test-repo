# 2d-icp-electron-diffusion-energy-experiment
#
# Reusable minimal 2-D ICP electron-particle diffusion baseline.
#
# Solved physics:
#   d(c_e)/dt       - div(D_e(mean_en) grad(c_e))             = 0
#   d(c_epsilon)/dt - div(D_epsilon(mean_en) grad(c_epsilon)) = 0
#
# c_epsilon is the conservative molar electron-energy state [eV mol/m^3].
# The closure derives mean_en = c_epsilon/c_e [eV] and uses that solved state
# to look up both particle and energy transport from electron_moments.txt.
#
# Electrostatic drift, Poisson, electron reactions, Joule heating, and
# volumetric energy sources are intentionally absent.
#
# Particle and energy wall losses use the same grounded thermal/sheath branch
# with potential=0.  The sheath suppression factor is therefore unity.

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
  [c_epsilon]
    type = MooseVariableFVReal
    # c_epsilon0 = c_e0 * 5.73276 eV
    initial_condition = 9.519471942731542e-08
    block = plasma
  []
[]

[AuxVariables]
  [electron_density]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
    block = plasma
  []
  [electron_temperature_eV]
    type = MooseVariableFVReal
    initial_condition = 3.82184
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
    prop_names = 'gas_pressure_Pa gas_temperature_K zero_phi'
    prop_values = '1.333223684 300.0 0.0'
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

  [electron_energy_density]
    type = ADParsedFunctorMaterial
    property_name = electron_energy_density_eV_m3
    functor_names = 'c_epsilon'
    functor_symbols = 'ceps'
    expression = '6.02214076e23*ceps'
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
    electron_mean_energy_output = mean_en_solved
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

  [electron_temperature_eV_material]
    type = ADParsedFunctorMaterial
    property_name = electron_temperature_eV_functor
    functor_names = 'mean_en_solved'
    functor_symbols = 'mean_en'
    expression = '(2.0/3.0)*mean_en'
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

  [energy_time]
    type = FVTimeKernel
    variable = c_epsilon
    block = plasma
  []

  [energy_diffusion]
    type = FVDiffusion
    variable = c_epsilon
    coeff = electron_energy_diffusion
    block = plasma
  []
[]

[FVBCs]
  [electron_thermal_wall_loss]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = log_e
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    mean_electron_energy = mean_en_solved
    potential = zero_phi
    log_molar_state = true
  []

  [electron_energy_thermal_wall_loss]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = c_epsilon
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    electron_density = c_e_molar
    mean_electron_energy = mean_en_solved
    potential = zero_phi
    molar_energy_state = true
  []
[]

[AuxKernels]
  [electron_density_copy]
    type = FunctorAux
    variable = electron_density
    functor = electron_density_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_temperature_copy]
    type = FunctorAux
    variable = electron_temperature_eV
    functor = electron_temperature_eV_functor
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_copy]
    type = FunctorAux
    variable = mean_energy_out
    functor = mean_en_solved
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
  [electron_energy_inventory_eV_mol]
    type = ADElementIntegralFunctorPostprocessor
    functor = c_epsilon
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
    functor = mean_en_solved
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_min_eV]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_max_eV]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = max
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
  [electron_wall_energy_rate_eV_mol_s]
    type = SideFVFluxBCIntegral
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    fvbcs = 'electron_energy_thermal_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[VectorPostprocessors]
  [final_profile]
    type = ElementValueSampler
    variable = 'electron_density c_epsilon mean_energy_out electron_temperature_eV diffusion_out'
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
  off_diagonals_in_auto_scaling = true
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
    show = 'electron_density electron_temperature_eV'
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
