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

# Issue #253 G1 Poisson subapp.
# Electron and heavy charge state are frozen for each Poisson solve.


[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [potential_plasma]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[AuxVariables]
  [c_epsilon_frozen]
    type = MooseVariableFVReal
    initial_condition = 3.0641593079832217e-08
  []
  [phi_anchor_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [log_e_frozen]
    type = MooseVariableFVReal
    initial_condition = -19.047104590109491
  []
  [w_O2p_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0000000000000001e-05
  []
  [w_Om_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0000000000000001e-05
  []
  [w_Op_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0000000000000001e-05
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
    prop_names = 'relative_permittivity'
    prop_values = '1.0'
  []
  [electron_density]
    type = ADParsedFunctorMaterial
    property_name = electron_density_m3
    functor_names = 'log_e_frozen'
    functor_symbols = 'loge'
    expression = '6.02214076e23*exp(loge)'
  []
  [gummel_mean_energy]
    type = ADParsedFunctorMaterial
    property_name = gummel_mean_energy_ev
    functor_names = 'c_epsilon_frozen log_e_frozen'
    functor_symbols = 'ceps loge'
    expression = 'ceps/max(exp(loge),1.0e-300)'
  []
  [electron_response_beta]
    type = ADParsedFunctorMaterial
    property_name = electron_response_beta
    functor_names = 'electron_density_m3 gummel_mean_energy_ev'
    functor_symbols = 'ne mean_ev'
    expression = '1.8095128179727827e-08*ne/((2.0/3.0)*max(mean_ev,1.0e-6))'
  []
  [gas_mixture_density]
    type = ADParsedFunctorMaterial
    property_name = rho_from_heavy
    functor_names = 'p_gas_from_heavy T_g_from_heavy'
    functor_symbols = 'prs tmp'
    expression = 'prs*0.032/(8.31446261815324*tmp)'
  []
  [plasma_charge_density]
    type = PhysicsPlasmaChargeDensityMaterial
    density = rho_from_heavy
    electron_density = electron_density_m3
    ion_ids = 'O2p Om Op'
    ion_mass_fractions = 'w_O2p_frozen w_Om_frozen w_Op_frozen'
    ion_molar_masses = '0.032 0.016 0.016'
    ion_charges = '1 -1 1'
  []
[]

[FVKernels]
  [phi_diffusion]
    type = FVDiffusion
    variable = potential_plasma
    coeff = relative_permittivity
  []
  [phi_charge_source]
    type = FVCoupledForce
    variable = potential_plasma
    v = poisson_charge_source
    coef = 1.0
  []
  [electron_response_topology_correction]
    type = FVElectronResponseTopologyCorrection
    variable = potential_plasma
    anchor = phi_anchor_frozen
    beta = electron_response_beta
    strength = 1
  graph_radius = 1
  shell_weights = '1'
  directional_band = false
  radial_component = 0
  axial_component = 1
  []
[]


[Postprocessors]
  [charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density
    execute_on = 'INITIAL FINAL'
  []
  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = min
    execute_on = 'INITIAL FINAL'
  []
  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = max
    execute_on = 'INITIAL FINAL'
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
  fixed_point_algorithm = 'picard'
  nl_rel_tol = 1.0e-10
  nl_abs_tol = 1.0e-12
  nl_max_its = 20
  automatic_scaling = true
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  console = false
[]


[FVBCs]
  [grounded_plasma_boundary]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    value = 0.0
  []
[]

[VectorPostprocessors]
  [potential_profile]
    type = ElementValueSampler
    variable = 'potential_plasma'
    sort_by = id
    execute_on = 'FINAL'
  []
[]
