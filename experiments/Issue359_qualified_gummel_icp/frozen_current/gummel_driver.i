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

# Issue #351 dedicated frozen-heavy Gummel driver.
# Heavy state enters this app once per outer heavy step and is unchanged during
# every inner electron/Poisson fixed-point iteration.


[Problem]
  solve = false
  kernel_coverage_check = false
[]

[AuxVariables]
  [w_O2p_h]
    type = MooseVariableFVReal
    initial_condition = 1.0000000000000001e-05
  []
  [w_Om_h]
    type = MooseVariableFVReal
    initial_condition = 1.0000000000000001e-05
  []
  [w_Op_h]
    type = MooseVariableFVReal
    initial_condition = 1.0000000000000001e-05
  []
  [potential_from_poisson]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [fp_phi_anchor_diag]
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
  [p_gas_h]
    type = MooseVariableFVReal
    initial_condition = 1.333223684
  []
  [T_g_h]
    type = MooseVariableFVReal
    initial_condition = 300
  []
[]

[FunctorMaterials]
  [fp_delta_phi_abs]
    type = ADParsedFunctorMaterial
    property_name = fp_delta_phi_abs
    functor_names = 'potential_from_poisson fp_phi_anchor_diag'
    functor_symbols = 'phi phi0'
    expression = 'abs(phi-phi0)'
  []
  [electron_temperature_diagnostic]
    type = ADParsedFunctorMaterial
    property_name = electron_temperature_diagnostic_K
    functor_names = 'mean_energy_out'
    functor_symbols = 'mean_ev'
    expression = '7736.3454143667204*mean_ev'
  []
  [charge_density_diagnostic]
    type = ADParsedFunctorMaterial
    property_name = plasma_charge_density_C_m3
    functor_names = 'p_gas_h T_g_h w_O2p_h w_Om_h w_Op_h electron_density_out'
    functor_symbols = 'prs tmp wp wm wo ne'
    expression = '1.6021766339999999e-19*((prs*0.032/(8.31446261815324*tmp))*6.0221407599999999e+23*(wp/0.032-wm/0.016+wo/0.016)-ne)'
  []
[]

[GummelIteration]
  [electron_poisson]
    electron_multiapp = electron
    electron_input_file = electron_sub.i

    poisson_multiapp = poisson
    poisson_input_file = poisson_sub.i

    electron_density_variable = log_e
    poisson_electron_density_variable = log_e_frozen

    poisson_potential_variable = potential_plasma
    electron_potential_variable = potential_from_poisson
    potential_transfer_mode = through_parent
    parent_potential_variable = potential_from_poisson

    electron_to_poisson_source_variables = 'c_epsilon'
    electron_to_poisson_variables = 'c_epsilon_frozen'

    parent_to_poisson_source_variables =
      'potential_from_poisson p_gas_h T_g_h w_O2p_h w_Om_h w_Op_h'
    parent_to_poisson_variables =
      'phi_anchor_frozen p_gas_from_heavy T_g_from_heavy w_O2p_frozen w_Om_frozen w_Op_frozen'

    poisson_to_parent_source_variables = 'phi_anchor_frozen'
    poisson_to_parent_variables = 'fp_phi_anchor_diag'

    electron_to_parent_source_variables =
      'electron_density_out mean_energy_out'
    electron_to_parent_variables =
      'electron_density_out mean_energy_out'
    relaxation_factor = 0.45000000000000001

    manage_convergence = true
    convergence_name = gummel_delta_phi
    delta_phi_postprocessor = fp_delta_phi_max
    delta_phi_abs_tol = 9.9999999999999995e-07
  parent_to_electron_source_variables = 'p_gas_h T_g_h'
  parent_to_electron_variables = 'p_gas_from_heavy T_g_from_heavy'
  []
[]

[Postprocessors]
  [fp_delta_phi_max]
    type = ADElementExtremeFunctorValue
    functor = fp_delta_phi_abs
    value_type = max
    execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'
  []
  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
  [cumulative_fixed_point_iterations]
    type = CumulativeValuePostprocessor
    postprocessor = fixed_point_iterations
    execute_on = 'TIMESTEP_END'
  []
  [potential_min]
    type = ADElementExtremeFunctorValue
    functor = potential_from_poisson
    value_type = min
    execute_on = 'TIMESTEP_END'
  []
  [potential_max]
    type = ADElementExtremeFunctorValue
    functor = potential_from_poisson
    value_type = max
    execute_on = 'TIMESTEP_END'
  []
  [electron_density_min]
    type = ADElementExtremeFunctorValue
    functor = electron_density_out
    value_type = min
    execute_on = 'TIMESTEP_END'
  []
  [electron_density_max]
    type = ADElementExtremeFunctorValue
    functor = electron_density_out
    value_type = max
    execute_on = 'TIMESTEP_END'
  []
  [electron_density_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_density_out
    execute_on = 'TIMESTEP_END'
  []
  [mean_energy_min]
    type = ADElementExtremeFunctorValue
    functor = mean_energy_out
    value_type = min
    execute_on = 'TIMESTEP_END'
  []
  [mean_energy_max]
    type = ADElementExtremeFunctorValue
    functor = mean_energy_out
    value_type = max
    execute_on = 'TIMESTEP_END'
  []
  [mean_energy_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mean_energy_out
    execute_on = 'TIMESTEP_END'
  []
  [electron_temperature_min_K]
    type = ADElementExtremeFunctorValue
    functor = electron_temperature_diagnostic_K
    value_type = min
    execute_on = 'TIMESTEP_END'
  []
  [electron_temperature_max_K]
    type = ADElementExtremeFunctorValue
    functor = electron_temperature_diagnostic_K
    value_type = max
    execute_on = 'TIMESTEP_END'
  []
  [electron_temperature_avg_K]
    type = ElementAverageFunctorPostprocessor
    functor = electron_temperature_diagnostic_K
    execute_on = 'TIMESTEP_END'
  []
  [charge_density_min]
    type = ADElementExtremeFunctorValue
    functor = plasma_charge_density_C_m3
    value_type = min
    execute_on = 'TIMESTEP_END'
  []
  [charge_density_max]
    type = ADElementExtremeFunctorValue
    functor = plasma_charge_density_C_m3
    value_type = max
    execute_on = 'TIMESTEP_END'
  []
  [charge_density_avg]
    type = ElementAverageFunctorPostprocessor
    functor = plasma_charge_density_C_m3
    execute_on = 'TIMESTEP_END'
  []
  [charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = plasma_charge_density_C_m3
    execute_on = 'TIMESTEP_END'
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

  fixed_point_min_its = 2
  fixed_point_max_its = 3000
  fixed_point_rel_tol = 1e-08
  fixed_point_abs_tol = 1.0e-12
  accept_on_max_fixed_point_iteration = false

  fixed_point_algorithm = steffensen
  transformed_variables = 'potential_from_poisson'
  multiapp_fixed_point_convergence = gummel_delta_phi
[]

[Outputs]
  [step_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
    execute_vector_postprocessors_on = 'NONE'
    new_row_tolerance = 1.0e-30
  []
  [final_csv]
    type = CSV
    execute_on = 'FINAL'
    execute_vector_postprocessors_on = 'FINAL'
  []
[]
