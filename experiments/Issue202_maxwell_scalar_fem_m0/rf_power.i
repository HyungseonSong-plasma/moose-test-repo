# Issue #202 RF absorbed-power validation fixture
#
# Peak-phasor convention:
#   E(t) = Re{ E_hat exp(+i omega t) }
#   Q_RF = 0.5 * sigma_R * |E_hat|^2
#
# This is a prescribed-material validation case. It is not the final oxygen
# plasma constitutive model and does not include copper skin/proximity physics.

mu0 = 1.2566370614359173e-6
eps0 = 8.8541878128e-12
frequency = 13.56e6
omega = ${fparse 2*3.141592653589793*frequency}
omega_mu0 = ${fparse omega*mu0}
wave_k2 = ${fparse omega*omega*mu0*eps0}

plasma_sigma_real = 5.0
plasma_sigma_imag = -10.0
plasma_eps_r = 1.0
cover_eps_r = 3.6
wafer_eps_r = 12.5
focus_eps_r = 8.0
b_plasma = ${fparse omega_mu0*plasma_sigma_real}

I_peak = 10.0
source_scale = 1.0
coil_dr = 0.009
coil_dz = 0.018
coil_area = ${fparse coil_dr*coil_dz}
J_coil = ${fparse I_peak/coil_area}
source_imag = ${fparse -source_scale*omega_mu0*J_coil}

[Mesh]
  coord_type = RZ
  rz_coord_axis = Y
  [base]
    type = FileMeshGenerator
    file = '../Issue18_qvt_plasma_mapping/qvt.msh'
  []
  [axis]
    type = ParsedGenerateSideset
    input = base
    combinatorial_geometry = 'abs(x) < 1e-12'
    normal = '-1 0 0'
    new_sideset_name = axis
  []
  [outer_right]
    type = ParsedGenerateSideset
    input = axis
    combinatorial_geometry = 'abs(x - 0.2565) < 1e-10'
    normal = '1 0 0'
    new_sideset_name = outer_right
  []
  [outer_bottom]
    type = ParsedGenerateSideset
    input = outer_right
    combinatorial_geometry = 'abs(y) < 1e-12'
    normal = '0 -1 0'
    new_sideset_name = outer_bottom
  []
  [outer_top]
    type = ParsedGenerateSideset
    input = outer_bottom
    combinatorial_geometry = 'abs(y - 0.45) < 1e-10'
    normal = '0 1 0'
    new_sideset_name = outer_top
  []
[]

[Variables]
  [E_real]
    order = FIRST
    family = LAGRANGE
  []
  [E_imag]
    order = FIRST
    family = LAGRANGE
  []
[]

[Functions]
  [zero_fn]
    type = ConstantFunction
    value = 0
  []
  [b_plasma_fn]
    type = ConstantFunction
    value = ${b_plasma}
  []
  [neg_a_vac_fn]
    type = ParsedFunction
    expression = '-(1/(x*x) - k2)'
    symbol_names = 'k2'
    symbol_values = '${wave_k2}'
  []
  [neg_a_plasma_fn]
    type = ParsedFunction
    expression = '-(1/(x*x) - k2*epsr - ommu*sigma_i)'
    symbol_names = 'k2 epsr ommu sigma_i'
    symbol_values = '${wave_k2} ${plasma_eps_r} ${omega_mu0} ${plasma_sigma_imag}'
  []
  [neg_a_cover_fn]
    type = ParsedFunction
    expression = '-(1/(x*x) - k2*epsr)'
    symbol_names = 'k2 epsr'
    symbol_values = '${wave_k2} ${cover_eps_r}'
  []
  [neg_a_wafer_fn]
    type = ParsedFunction
    expression = '-(1/(x*x) - k2*epsr)'
    symbol_names = 'k2 epsr'
    symbol_values = '${wave_k2} ${wafer_eps_r}'
  []
  [neg_a_focus_fn]
    type = ParsedFunction
    expression = '-(1/(x*x) - k2*epsr)'
    symbol_names = 'k2 epsr'
    symbol_values = '${wave_k2} ${focus_eps_r}'
  []
[]

[Materials]
  [vacuum_like]
    type = GenericFunctionMaterial
    prop_names = 'neg_a b'
    prop_values = 'neg_a_vac_fn zero_fn'
    block = 'vacuum metal electrode top right bottom port coil1 coil2 coil3'
  []
  [plasma]
    type = GenericFunctionMaterial
    prop_names = 'neg_a b'
    prop_values = 'neg_a_plasma_fn b_plasma_fn'
    block = plasma
  []
  [cover]
    type = GenericFunctionMaterial
    prop_names = 'neg_a b'
    prop_values = 'neg_a_cover_fn zero_fn'
    block = cover
  []
  [wafer]
    type = GenericFunctionMaterial
    prop_names = 'neg_a b'
    prop_values = 'neg_a_wafer_fn zero_fn'
    block = wafer
  []
  [focus_ring]
    type = GenericFunctionMaterial
    prop_names = 'neg_a b'
    prop_values = 'neg_a_focus_fn zero_fn'
    block = focus_ring
  []

  # Peak-phasor collisional RF heating density [W/m^3]. sigma_I does not
  # appear explicitly: it changes the field reactively but is not dissipative.
  [rf_power_density]
    type = ParsedMaterial
    property_name = q_rf
    coupled_variables = 'E_real E_imag'
    constant_names = 'sigma_r'
    constant_expressions = '${plasma_sigma_real}'
    expression = '0.5*sigma_r*(E_real^2 + E_imag^2)'
    block = plasma
  []
[]

[Kernels]
  [E_real_diffusion]
    type = Diffusion
    variable = E_real
  []
  [E_imag_diffusion]
    type = Diffusion
    variable = E_imag
  []
  [E_real_reaction]
    type = MatReaction
    variable = E_real
    reaction_rate = neg_a
  []
  [E_imag_reaction]
    type = MatReaction
    variable = E_imag
    reaction_rate = neg_a
  []
  [E_real_sigma_coupling]
    type = MatCoupledForce
    variable = E_real
    v = 'E_imag'
    coef = '1'
    material_properties = 'b'
  []
  [E_imag_sigma_coupling]
    type = MatCoupledForce
    variable = E_imag
    v = 'E_real'
    coef = '-1'
    material_properties = 'b'
  []
  [coil1_current]
    type = BodyForce
    variable = E_imag
    block = coil1
    value = ${source_imag}
  []
  [coil2_current]
    type = BodyForce
    variable = E_imag
    block = coil2
    value = ${source_imag}
  []
  [coil3_current]
    type = BodyForce
    variable = E_imag
    block = coil3
    value = ${source_imag}
  []
[]

[BCs]
  [axis_real]
    type = DirichletBC
    variable = E_real
    boundary = axis
    value = 0
  []
  [axis_imag]
    type = DirichletBC
    variable = E_imag
    boundary = axis
    value = 0
  []
  [wall_real]
    type = DirichletBC
    variable = E_real
    boundary = 'outer_right outer_bottom outer_top'
    value = 0
  []
  [wall_imag]
    type = DirichletBC
    variable = E_imag
    boundary = 'outer_right outer_bottom outer_top'
    value = 0
  []
[]

[Postprocessors]
  [E_real_l2]
    type = ElementL2Norm
    variable = E_real
  []
  [E_imag_l2]
    type = ElementL2Norm
    variable = E_imag
  []
  [P_abs]
    type = ElementIntegralMaterialProperty
    mat_prop = q_rf
    block = plasma
  []
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_abs_tol = 1e-12
  nl_rel_tol = 1e-10
  nl_max_its = 20
  l_tol = 1e-12
  l_max_its = 500
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]

[Outputs]
  exodus = true
  csv = true
[]
