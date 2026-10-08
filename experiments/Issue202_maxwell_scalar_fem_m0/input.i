# Issue #202 M0/M1 scalar-RZ FEM Maxwell baseline
#
# Convention:
#   E(t) = Re{ E_hat exp(+i omega t) }
#   E_hat = E_real + i E_imag
#
# Baseline PDE (mu = mu0, multiplied through by mu0):
#   -laplacian_RZ(E_theta) + E_theta/r^2
#   + (i omega mu0 sigma - omega^2 mu0 epsilon) E_theta
#   = -i omega mu0 J_theta^e
#
# This first runtime surface is the vacuum/source discriminator:
#   epsilon_r = 1, sigma = 0 everywhere
#   coil1/coil2/coil3 carry the same prescribed peak current phasor.
# Copper skin/proximity physics and plasma feedback are intentionally OFF.

pi = 3.141592653589793
mu0 = ${fparse 4*pi*1e-7}
eps0 = 8.8541878128e-12
frequency = 13.56e6
omega = ${fparse 2*pi*frequency}

# One physical turn per named RZ coil block.
I_peak = 10.0
coil_dr = 0.009
coil_dz = 0.018
coil_area = ${fparse coil_dr*coil_dz}
J_coil = ${fparse I_peak/coil_area}
source_imag = ${fparse -omega*mu0*J_coil}
wave_k2 = ${fparse omega*omega*mu0*eps0}

[Mesh]
  coord_type = RZ
  rz_coord_axis = Y

  [base]
    type = FileMeshGenerator
    file = '../Issue18_qvt_plasma_mapping/qvt.msh'
  []

  # r = x because the RZ symmetry axis is Y.  E_theta = 0 here is a
  # regularity condition, not a physical wall condition.
  [axis]
    type = ParsedGenerateSideset
    input = base
    combinatorial_geometry = 'abs(x) < 1e-12'
    normal = '-1 0 0'
    new_sideset_name = axis
  []

  # Initial simple truncation boundary.  Domain-size sensitivity is an M2 gate.
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
  # MatReaction contributes -L*u, so the material property supplied below is
  # neg_a = -(1/r^2 - omega^2 mu0 eps0) in this vacuum baseline.
  [neg_a_fn]
    type = ParsedFunction
    expression = '-(1/(x*x) - k2)'
    symbol_names = 'k2'
    symbol_values = '${wave_k2}'
  []

  # b = omega mu0 sigma_R.  Zero for this first vacuum/source discriminator.
  [b_fn]
    type = ConstantFunction
    value = 0
  []
[]

[Materials]
  [maxwell_coefficients]
    type = GenericFunctionMaterial
    prop_names = 'neg_a b'
    prop_values = 'neg_a_fn b_fn'
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

  # General real/imag conductivity-coupling route retained in the baseline.
  # Real equation:  L(E_R) + a E_R - b E_I = 0
  #                 => L(E_R) + a E_R = +b E_I
  [E_real_sigma_coupling]
    type = MatCoupledForce
    variable = E_real
    v = 'E_imag'
    coef = '1'
    material_properties = 'b'
  []

  # Imag equation:  L(E_I) + a E_I + b E_R = S_I
  #                 => L(E_I) + a E_I = -b E_R + S_I
  [E_imag_sigma_coupling]
    type = MatCoupledForce
    variable = E_imag
    v = 'E_real'
    coef = '-1'
    material_properties = 'b'
  []

  # Three separate impressed-current objects are intentional.  They share one
  # series-coil current but remain independently switchable for discriminators.
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

  [outer_real]
    type = DirichletBC
    variable = E_real
    boundary = 'outer_right outer_bottom outer_top'
    value = 0
  []
  [outer_imag]
    type = DirichletBC
    variable = E_imag
    boundary = 'outer_right outer_bottom outer_top'
    value = 0
  []
[]

[Postprocessors]
  [E_real_min]
    type = ElementExtremeValue
    variable = E_real
    value_type = min
  []
  [E_real_max]
    type = ElementExtremeValue
    variable = E_real
    value_type = max
  []
  [E_real_l2]
    type = ElementL2Norm
    variable = E_real
  []
  [E_imag_min]
    type = ElementExtremeValue
    variable = E_imag
    value_type = min
  []
  [E_imag_max]
    type = ElementExtremeValue
    variable = E_imag
    value_type = max
  []
  [E_imag_l2]
    type = ElementL2Norm
    variable = E_imag
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
