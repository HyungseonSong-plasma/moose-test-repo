# Issue #376 T4 -- one implicit FEM electron-energy step for the segregated
# state-dependent Maxwell/plasma fixed-point discriminator.
#
# The outer T4 driver owns the scalar conductivity closure and Picard loop.
# This input owns the actual 2-D MOOSE transfer and electron-energy update.
# The previous physical state is intentionally re-applied on every Picard
# iteration so the fixed point solves one implicit physical timestep rather
# than repeatedly accumulating pseudo-time heating.

rf_scale = 1.0
source_enable = 0.0
plasma_sigma_real = 5.0
faraday_J_per_eV_mol = 96485.33212331001
dt_t4 = 1.0e-6
energy_initial_log = -18.829829186913098
maxwell_solution_file = 'results_t4/seed/maxwell.e'

[Mesh]
  coord_type = RZ
  rz_coord_axis = Y
  [base]
    type = FileMeshGenerator
    file = '../fem_fvm_plasma_discriminator/plasma_contour_l3_4p5mm.msh'
  []
[]

[Variables]
  [log_energy]
    family = LAGRANGE
    order = FIRST
    initial_condition = ${energy_initial_log}
    block = plasma
  []
[]

[AuxVariables]
  [E_real_rf]
    family = LAGRANGE
    order = FIRST
    block = plasma
  []
  [E_imag_rf]
    family = LAGRANGE
    order = FIRST
    block = plasma
  []
[]

[UserObjects]
  [maxwell_solution]
    type = SolutionUserObject
    mesh = '${maxwell_solution_file}'
    system_variables = 'E_real E_imag'
    timestep = LATEST
    execute_on = INITIAL
  []
[]

[AuxKernels]
  [map_E_real]
    type = SolutionAux
    variable = E_real_rf
    solution = maxwell_solution
    from_variable = E_real
    execute_on = INITIAL
  []
  [map_E_imag]
    type = SolutionAux
    variable = E_imag_rf
    solution = maxwell_solution
    from_variable = E_imag
    execute_on = INITIAL
  []
[]

[FunctorMaterials]
  [electron_molar_energy_density]
    type = ADParsedFunctorMaterial
    property_name = electron_molar_energy_density
    functor_names = 'log_energy'
    functor_symbols = 'ue'
    expression = 'exp(ue)'
    block = plasma
  []
[]

[Materials]
  [rf_power_raw]
    type = ParsedMaterial
    property_name = q_rf_raw
    coupled_variables = 'E_real_rf E_imag_rf'
    constant_names = 'sigma_r'
    constant_expressions = '${plasma_sigma_real}'
    expression = '0.5*sigma_r*(E_real_rf^2 + E_imag_rf^2)'
    block = plasma
  []

  [rf_power_scaled]
    type = ParsedMaterial
    property_name = q_rf_scaled
    coupled_variables = 'E_real_rf E_imag_rf'
    constant_names = 'sigma_r scale'
    constant_expressions = '${plasma_sigma_real} ${rf_scale}'
    expression = 'scale*0.5*sigma_r*(E_real_rf^2 + E_imag_rf^2)'
    block = plasma
  []

  [rf_energy_source]
    type = ParsedMaterial
    property_name = q_rf_eV_mol
    coupled_variables = 'E_real_rf E_imag_rf'
    constant_names = 'sigma_r scale enabled F'
    constant_expressions = '${plasma_sigma_real} ${rf_scale} ${source_enable} ${faraday_J_per_eV_mol}'
    expression = 'enabled*scale*0.5*sigma_r*(E_real_rf^2 + E_imag_rf^2)/F'
    block = plasma
  []
[]

[Kernels]
  [energy_time]
    type = PhysicsFEMLogMolarTimeDerivative
    variable = log_energy
    block = plasma
  []

  # RF heating remains a distinct owner from electrostatic electron work.
  [rf_heating]
    type = MatBodyForce
    variable = log_energy
    material_property = q_rf_eV_mol
    block = plasma
  []
[]

[Postprocessors]
  [P_rf_raw_W]
    type = ElementIntegralMaterialProperty
    mat_prop = q_rf_raw
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [P_rf_scaled_W]
    type = ElementIntegralMaterialProperty
    mat_prop = q_rf_scaled
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [S_rf_eV_mol_s]
    type = ElementIntegralMaterialProperty
    mat_prop = q_rf_eV_mol
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_energy_inventory_eV_mol]
    type = ADElementIntegralFunctorPostprocessor
    functor = electron_molar_energy_density
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_energy_min_eV_mol_m3]
    type = ADElementExtremeFunctorValue
    functor = electron_molar_energy_density
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_energy_max_eV_mol_m3]
    type = ADElementExtremeFunctorValue
    functor = electron_molar_energy_density
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = ${dt_t4}
  end_time = ${dt_t4}
  nl_rel_tol = 1e-11
  nl_abs_tol = 1e-13
  nl_max_its = 30
  l_tol = 1e-12
  l_max_its = 100
  petsc_options_iname = '-ksp_type -pc_type'
  petsc_options_value = 'preonly lu'
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Outputs]
  csv = true
  exodus = false
  execute_on = 'INITIAL TIMESTEP_END'
[]
