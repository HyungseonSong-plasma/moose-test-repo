# Issue #202 M2-G prescribed-material chamber cross-solver case
#
# This is a validation fixture, not the final physical plasma/copper model.
# It activates the real/imaginary conductivity coupling in the plasma and
# piecewise dielectric coefficients on the existing QVT chamber geometry.
#
# Convention:
#   E(t) = Re{ E_hat exp(+i omega t) }
#   E_hat = E_real + i E_imag
#
# PDE (mu = mu0, multiplied through by mu0):
#   -laplacian_RZ(E_theta) + E_theta/r^2
#   + (i omega mu0 sigma - omega^2 mu0 epsilon) E_theta
#   = -i omega mu0 J_theta^e

mu0 = 1.2566370614359173e-6
eps0 = 8.8541878128e-12
frequency = 13.56e6
omega = ${fparse 2*3.141592653589793*frequency}
omega_mu0 = ${fparse omega*mu0}
wave_k2 = ${fparse omega*omega*mu0*eps0}

# Prescribed validation materials.  The plasma conductivity is deliberately
# complex so that both real/imaginary coupled equations are exercised.
plasma_sigma_real = 5.0
plasma_sigma_imag = -10.0
plasma_eps_r = 1.0
cover_eps_r = 3.6
wafer_eps_r = 12.5
focus_eps_r = 8.0
b_plasma = ${fparse omega_mu0*plasma_sigma_real}

# Three physical turns of one prescribed-current series coil.
I_peak = 10.0
coil_dr = 0.009
coil_dz = 0.018
coil_area = ${fparse coil_dr*coil_dz}
J_coil = ${fparse I_peak/coil_area}
source_imag = ${fparse -omega_mu0*J_coil}

mesh_refine = 0

[Mesh]
  coord_type = RZ
  rz_coord_axis = Y
  uniform_refine = ${mesh_refine}

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

  # MatReaction contributes -reaction_rate*u.  Therefore each material
  # supplies neg_a = -a, where
  #   a = 1/r^2 - k0^2*eps_r - omega*mu0*sigma_I.
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
  # Plasma probes
  [E_real_p1]
    type = PointValue
    variable = E_real
    point = '0.05 0.15 0'
  []
  [E_imag_p1]
    type = PointValue
    variable = E_imag
    point = '0.05 0.15 0'
  []
  [E_real_p2]
    type = PointValue
    variable = E_real
    point = '0.12 0.15 0'
  []
  [E_imag_p2]
    type = PointValue
    variable = E_imag
    point = '0.12 0.15 0'
  []
  [E_real_p3]
    type = PointValue
    variable = E_real
    point = '0.20 0.15 0'
  []
  [E_imag_p3]
    type = PointValue
    variable = E_imag
    point = '0.20 0.15 0'
  []
  [E_real_p4]
    type = PointValue
    variable = E_real
    point = '0.05 0.28 0'
  []
  [E_imag_p4]
    type = PointValue
    variable = E_imag
    point = '0.05 0.28 0'
  []
  [E_real_p5]
    type = PointValue
    variable = E_real
    point = '0.12 0.28 0'
  []
  [E_imag_p5]
    type = PointValue
    variable = E_imag
    point = '0.12 0.28 0'
  []
  [E_real_p6]
    type = PointValue
    variable = E_real
    point = '0.20 0.28 0'
  []
  [E_imag_p6]
    type = PointValue
    variable = E_imag
    point = '0.20 0.28 0'
  []

  # Quartz-cover probes
  [E_real_q1]
    type = PointValue
    variable = E_real
    point = '0.03 0.33 0'
  []
  [E_imag_q1]
    type = PointValue
    variable = E_imag
    point = '0.03 0.33 0'
  []
  [E_real_q2]
    type = PointValue
    variable = E_real
    point = '0.09 0.33 0'
  []
  [E_imag_q2]
    type = PointValue
    variable = E_imag
    point = '0.09 0.33 0'
  []
  [E_real_q3]
    type = PointValue
    variable = E_real
    point = '0.15 0.33 0'
  []
  [E_imag_q3]
    type = PointValue
    variable = E_imag
    point = '0.15 0.33 0'
  []
  [E_real_q4]
    type = PointValue
    variable = E_real
    point = '0.21 0.33 0'
  []
  [E_imag_q4]
    type = PointValue
    variable = E_imag
    point = '0.21 0.33 0'
  []

  # Vacuum probes above the cover/coils
  [E_real_v1]
    type = PointValue
    variable = E_real
    point = '0.03 0.39 0'
  []
  [E_imag_v1]
    type = PointValue
    variable = E_imag
    point = '0.03 0.39 0'
  []
  [E_real_v2]
    type = PointValue
    variable = E_real
    point = '0.09 0.39 0'
  []
  [E_imag_v2]
    type = PointValue
    variable = E_imag
    point = '0.09 0.39 0'
  []
  [E_real_v3]
    type = PointValue
    variable = E_real
    point = '0.15 0.39 0'
  []
  [E_imag_v3]
    type = PointValue
    variable = E_imag
    point = '0.15 0.39 0'
  []
  [E_real_v4]
    type = PointValue
    variable = E_real
    point = '0.21 0.39 0'
  []
  [E_imag_v4]
    type = PointValue
    variable = E_imag
    point = '0.21 0.39 0'
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
