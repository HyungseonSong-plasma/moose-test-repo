# Issue #202 M2-C conducting-cylinder / skin-depth verification
#
# Axisymmetric, z-invariant conducting cylinder driven by a prescribed
# azimuthal electric field at r=R.  For exp(+i omega t) and real sigma,
#
#   d2E/dr2 + (1/r)dE/dr - E/r^2 + kappa^2 E = 0
#   kappa^2 = omega^2 mu0 epsilon - i omega mu0 sigma
#
# with regularity E(0)=0 and E(R)=1.  The exact solution is
#
#   E(r) = J1(kappa r) / J1(kappa R).
#
# This case directly tests the scalar-RZ geometric term and real/imaginary
# conductivity coupling independently of coil and plasma-feedback semantics.

mu0 = 1.2566370614359173e-6
eps0 = 8.8541878128e-12
frequency = 13.56e6
omega = ${fparse 2*3.141592653589793*frequency}
sigma_R = 100.0
radius = 0.05
height = 0.01
wave_k2 = ${fparse omega*omega*mu0*eps0}
b_sigma = ${fparse omega*mu0*sigma_R}
mesh_refine = 0

[Mesh]
  coord_type = RZ
  rz_coord_axis = Y
  uniform_refine = ${mesh_refine}
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 100
    ny = 2
    xmin = 0
    xmax = ${radius}
    ymin = 0
    ymax = ${height}
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
  [neg_a_fn]
    type = ParsedFunction
    expression = '-(1/(x*x) - k2)'
    symbol_names = 'k2'
    symbol_values = '${wave_k2}'
  []
  [b_fn]
    type = ConstantFunction
    value = ${b_sigma}
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

  # L(E_R) + a E_R - b E_I = 0  -> L(E_R)+aE_R = +bE_I
  [E_real_sigma_coupling]
    type = MatCoupledForce
    variable = E_real
    v = E_imag
    coef = 1
    material_properties = b
  []

  # L(E_I) + a E_I + b E_R = 0  -> L(E_I)+aE_I = -bE_R
  [E_imag_sigma_coupling]
    type = MatCoupledForce
    variable = E_imag
    v = E_real
    coef = -1
    material_properties = b
  []
[]

[BCs]
  # Axis regularity for an azimuthal vector component.
  [axis_real]
    type = DirichletBC
    variable = E_real
    boundary = left
    value = 0
  []
  [axis_imag]
    type = DirichletBC
    variable = E_imag
    boundary = left
    value = 0
  []

  # Real unit-amplitude surface drive; top/bottom remain natural so the
  # analytical solution is z-invariant.
  [drive_real]
    type = DirichletBC
    variable = E_real
    boundary = right
    value = 1
  []
  [drive_imag]
    type = DirichletBC
    variable = E_imag
    boundary = right
    value = 0
  []
[]

[Postprocessors]
  [E_real_r01]
    type = PointValue
    variable = E_real
    point = '0.01 0.005 0'
  []
  [E_imag_r01]
    type = PointValue
    variable = E_imag
    point = '0.01 0.005 0'
  []
  [E_real_r02]
    type = PointValue
    variable = E_real
    point = '0.02 0.005 0'
  []
  [E_imag_r02]
    type = PointValue
    variable = E_imag
    point = '0.02 0.005 0'
  []
  [E_real_r03]
    type = PointValue
    variable = E_real
    point = '0.03 0.005 0'
  []
  [E_imag_r03]
    type = PointValue
    variable = E_imag
    point = '0.03 0.005 0'
  []
  [E_real_r04]
    type = PointValue
    variable = E_real
    point = '0.04 0.005 0'
  []
  [E_imag_r04]
    type = PointValue
    variable = E_imag
    point = '0.04 0.005 0'
  []
  [E_real_r045]
    type = PointValue
    variable = E_real
    point = '0.045 0.005 0'
  []
  [E_imag_r045]
    type = PointValue
    variable = E_imag
    point = '0.045 0.005 0'
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
  nl_rel_tol = 1e-11
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
