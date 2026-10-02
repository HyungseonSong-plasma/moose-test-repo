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

# Issue #253 G2: solved electron-energy + Joule + O2-elastic timestep sweep.
# COMSOL-consistent electron particle/energy wall fluxes are always ON.
# Joule heating and O2 elastic energy exchange are ON; heavy evolution is frozen.
# Sequence 12 compares chi=1,10,20 at equal T=100 initial dielectric-relaxation times.


[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [log_e]
    type = MooseVariableFVReal
    initial_condition = -19.047104590109491
  []
  [c_epsilon]
    type = MooseVariableFVReal
    initial_condition = 3.0641593079832217e-08
  []
[]

[AuxVariables]
  [w_O2p_h]
    type = MooseVariableFVReal
    initial_condition = 3.8523381586724929e-05
  []
  [w_Om_h]
    type = MooseVariableFVReal
    initial_condition = 0.001
  []
  [w_Op_h]
    type = MooseVariableFVReal
    initial_condition = 0.001
  []
  [potential_from_poisson]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [electron_density_out]
    type = MooseVariableFVReal
    initial_condition = 3218833278166041
  []
  [mean_energy_out]
    type = MooseVariableFVReal
    initial_condition = 5.7327599999999999
  []
  [mobility_out]
    type = MooseVariableFVReal
    initial_condition = 9755.114369721427
  []
  [diffusion_out]
    type = MooseVariableFVReal
    initial_condition = 41257.29899041419
  []
  [elastic_loss_candidate_out]
    type = MooseVariableFVReal
    initial_condition = 4.622905967454569
  []
  [p_gas_from_heavy]
    type = MooseVariableFVReal
    initial_condition = 1.333223684
  []
  [T_g_from_heavy]
    type = MooseVariableFVReal
    initial_condition = 300
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'carrier_one zero_flux'
    prop_values = '1.0 0.0'
  []

  [electron_molar_density]
    type = ADParsedFunctorMaterial
    property_name = c_e_molar
    functor_names = 'log_e'
    functor_symbols = 'loge'
    expression = 'exp(loge)'
  []

  [electron_number_density]
    type = ADParsedFunctorMaterial
    property_name = electron_density_m3
    functor_names = 'log_e'
    functor_symbols = 'loge'
    expression = '6.02214076e23*exp(loge)'
  []




  [joule_transport_switch]
    type = ADParsedFunctorMaterial
    property_name = joule_mobility
    functor_names = 'electron_mobility'
    functor_symbols = 'mu'
    expression = '1.0*mu'
  []

  [joule_diffusion_switch]
    type = ADParsedFunctorMaterial
    property_name = joule_diffusion
    functor_names = 'electron_diffusion'
    functor_symbols = 'diff'
    expression = '1.0*diff'
  []

  [electron_sheath_factor]
    type = ADParsedFunctorMaterial
    property_name = electron_sheath_factor
    functor_names = 'potential_from_poisson mean_en_solved'
    functor_symbols = 'phi mean_ev'
    expression = 'exp(-(0.5*(phi+abs(phi)))/((2.0/3.0)*mean_ev))'
  []
  [thermal_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = thermal_flux_molar_outward
    functor_names = 'log_e mean_en_solved electron_sheath_factor'
    functor_symbols = 'loge mean_ev sheath'
    expression = '0.5*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))*sheath'
  []
  [sheath_energy_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = sheath_energy_flux_outward
    functor_names = 'c_epsilon mean_en_solved electron_sheath_factor'
    functor_symbols = 'eps_hat mean_ev sheath'
    expression = '0.83333333333333333*eps_hat*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))*sheath'
  []

  [electron_energy_density_physical]
    type = ADParsedFunctorMaterial
    property_name = electron_energy_J_m3
    functor_names = 'c_epsilon'
    functor_symbols = 'ceps'
    expression = '96485.332123310014*ceps'
  []


  [elastic_energy_candidate]
    type = ADParsedFunctorMaterial
    property_name = S_elastic_candidate_molar
    functor_names = 'mean_en_solved T_g_from_heavy R_elastic_O2'
    functor_symbols = 'meanE tgas rprog'
    expression = '-5.1429366526835038e-05*(0.66666666666666663*meanE-8.6173332621449999e-05*tgas)*rprog'
  []

  [elastic_energy_applied]
    type = ADParsedFunctorMaterial
    property_name = S_elastic_applied_molar
    functor_names = 'S_elastic_candidate_molar'
    functor_symbols = 'source'
    expression = '1.0*source'
  []

  [elastic_loss_candidate_physical]
    type = ADParsedFunctorMaterial
    property_name = elastic_loss_candidate_W_m3
    functor_names = 'S_elastic_candidate_molar'
    functor_symbols = 'source'
    expression = '-source*96485.332123310014'
  []

  [elastic_loss_applied_physical]
    type = ADParsedFunctorMaterial
    property_name = elastic_loss_applied_W_m3
    functor_names = 'S_elastic_applied_molar'
    functor_symbols = 'source'
    expression = '-source*96485.332123310014'
  []
  [electron_energy_density_eV]
    type = ADParsedFunctorMaterial
    property_name = electron_energy_density_eV_m3
    functor_names = 'c_epsilon'
    functor_symbols = 'ceps'
    expression = '6.0221407599999999e+23*ceps'
  []
  [oxygen_molar_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2
    functor_names = 'p_gas_from_heavy T_g_from_heavy'
    functor_symbols = 'prs tmp'
    expression = '0.99994*prs/(8.31446261815324*tmp)'
  []
  [electron_transport_closure]
    type = PhysicsElectronClosureMaterial
    state_form = physical_eV
    electron_number_density = electron_density_m3
    electron_energy_density = electron_energy_density_eV_m3
    gas_pressure = p_gas_from_heavy
    gas_temperature = T_g_from_heavy
    transport_table_file = electron_moments.txt
    lookup_bounds_policy = error
    electron_mean_energy_output = mean_en_solved
    electron_temperature_output = electron_temperature_K
    neutral_number_density_output = neutral_number_density
    electron_reduced_mobility_output = electron_reduced_mobility
    electron_reduced_diffusion_output = electron_reduced_diffusion
    electron_mobility_output = electron_mobility
    electron_diffusion_output = electron_diffusion
    electron_energy_mobility_output = electron_energy_mobility
    electron_energy_diffusion_output = electron_energy_diffusion
  []
  [electron_o2_elastic_kinetics]
    type = PhysicsElectronKineticsMaterial
    electron_mean_energy = mean_en_solved
    electron_number_density = electron_density_m3
    rate_table_files = 'o2_elastic.txt'
    target_molar_concentrations = 'c_O2'
    reaction_progress_names = 'R_elastic_O2'
  []
[]

[FVKernels]
  [electron_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_e
  []
  [electron_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_e
    coeff = electron_diffusion
    coeff_interp_method = harmonic
  []
  [electron_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_e
    potential = potential_from_poisson
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
  []

  [energy_time]
    type = FVTimeKernel
    variable = c_epsilon
  []
  [energy_diffusion]
    type = FVDiffusion
    variable = c_epsilon
    coeff = electron_energy_diffusion
  []
  [energy_drift]
    type = PhysicsFVElectrostaticDrift
    variable = c_epsilon
    potential = potential_from_poisson
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
  []
  [energy_joule]
    type = PhysicsFVElectronEnergyJouleHeating
    variable = c_epsilon
    electron_density = c_e_molar
    potential = potential_from_poisson
    mobility = joule_mobility
    diffusion = joule_diffusion
  state_form = molar_eV
  []
  [energy_elastic_o2]
    type = FVCoupledForce
    variable = c_epsilon
    v = S_elastic_applied_molar
    coef = 1.0
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
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mobility_copy]
    type = FunctorAux
    variable = mobility_out
    functor = electron_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [diffusion_copy]
    type = FunctorAux
    variable = diffusion_out
    functor = electron_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_loss_candidate_copy]
    type = FunctorAux
    variable = elastic_loss_candidate_out
    functor = elastic_loss_candidate_W_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]


[Postprocessors]
  [electron_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = c_e_molar
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [energy_inventory_J_m2]
    type = ADElementIntegralFunctorPostprocessor
    functor = electron_energy_J_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_avg_eV]
    type = ElementAverageFunctorPostprocessor
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_min_eV]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_max_eV]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_mobility_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_loss_candidate_W_m2]
    type = ADElementIntegralFunctorPostprocessor
    functor = elastic_loss_candidate_W_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [elastic_loss_applied_W_m2]
    type = ADElementIntegralFunctorPostprocessor
    functor = elastic_loss_applied_W_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_e_min]
    type = ADElementExtremeFunctorValue
    functor = electron_density_m3
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_e_max]
    type = ADElementExtremeFunctorValue
    functor = electron_density_m3
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_from_poisson
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_from_poisson
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_wall_particle_rate]
    type = SideFVFluxBCIntegral
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    fvbcs = 'electron_wall_collection'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_wall_energy_rate]
    type = SideFVFluxBCIntegral
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    fvbcs = 'electron_energy_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[VectorPostprocessors]
  [energy_profile]
    type = ElementValueSampler
    variable = 'electron_density_out potential_from_poisson c_epsilon mean_energy_out mobility_out diffusion_out elastic_loss_candidate_out'
    sort_by = id
    execute_on = 'FINAL'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 5.6650790022617894e-11
  dtmin = 5.6650790022617894e-11
  dtmax = 5.6650790022617894e-11
  end_time = 2.2660316009047157e-10
  num_steps = 4
  timestep_tolerance = 1.0e-18
  nl_rel_tol = 1.0e-9
  # Use MOOSE variable/equation scaling so the nonlinear norm is not biased by
  # the 1/dt magnitude of the transient terms when chi is changed.
  nl_abs_tol = 1.0e-13
  nl_max_its = 80
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = true
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  [final_csv]
    type = CSV
    execute_on = 'FINAL'
    execute_vector_postprocessors_on = 'FINAL'
  []
  [final_exodus]
    type = Exodus
    execute_on = 'FINAL'
  []
[]


[FVBCs]
  [electron_wall_collection]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = log_e
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    mean_electron_energy = mean_en_solved
    potential = potential_from_poisson
    log_molar_state = true
  []
  [electron_energy_wall_loss]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = c_epsilon
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    electron_density = c_e_molar
    mean_electron_energy = mean_en_solved
    potential = potential_from_poisson
    molar_energy_state = true
  []
[]
