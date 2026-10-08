# Issue #202 M2-D dielectric/material-interface verification
#
# Independent 1D planar Helmholtz material test.  M2-C already verifies the
# scalar-RZ geometric term and complex conductivity coupling; this case isolates
# discontinuous epsilon placement and conformal-interface continuity.
#
#   -d2E/dx2 - k_i^2 E = 0
#   k_i^2 = omega^2 mu0 epsilon0 epsilon_r,i
#
# epsilon_r = 1 on 0 <= x < 0.025 m
# epsilon_r = 4 on 0.025 <= x <= 0.05 m
# E(0)=0, E(L)=1.  With constant mu, both E and dE/dx are continuous at the
# conformal interface and no explicit interface BC is applied.

mu0 = 1.2566370614359173e-6
eps0 = 8.8541878128e-12
frequency = 1.0e9
omega = ${fparse 2*3.141592653589793*frequency}
eps_r_1 = 1.0
eps_r_2 = 4.0
k2_1 = ${fparse omega*omega*mu0*eps0*eps_r_1}
k2_2 = ${fparse omega*omega*mu0*eps0*eps_r_2}
mesh_refine = 0

[Mesh]
  uniform_refine = ${mesh_refine}
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 100
    xmin = 0
    xmax = 0.05
  []
  [layer2]
    type = SubdomainBoundingBoxGenerator
    input = gen
    location = INSIDE
    bottom_left = '0.025 -1 -1'
    top_right = '0.051 1 1'
    block_id = 2
  []
[]

[Variables]
  [E]
    order = FIRST
    family = LAGRANGE
  []
[]

[Materials]
  # MatReaction contributes -reaction_rate*E, so reaction_rate=k^2 gives
  # the required -k^2 E Helmholtz term.
  [layer1_coeff]
    type = GenericConstantMaterial
    block = 0
    prop_names = neg_a
    prop_values = ${k2_1}
  []
  [layer2_coeff]
    type = GenericConstantMaterial
    block = 2
    prop_names = neg_a
    prop_values = ${k2_2}
  []
[]

[Kernels]
  [diffusion]
    type = Diffusion
    variable = E
  []
  [reaction]
    type = MatReaction
    variable = E
    reaction_rate = neg_a
  []
[]

[BCs]
  [left]
    type = DirichletBC
    variable = E
    boundary = left
    value = 0
  []
  [right]
    type = DirichletBC
    variable = E
    boundary = right
    value = 1
  []
[]

[Postprocessors]
  [E_x01]
    type = PointValue
    variable = E
    point = '0.01 0 0'
  []
  [E_x02]
    type = PointValue
    variable = E
    point = '0.02 0 0'
  []
  [E_interface]
    type = PointValue
    variable = E
    point = '0.025 0 0'
  []
  [E_x03]
    type = PointValue
    variable = E
    point = '0.03 0 0'
  []
  [E_x04]
    type = PointValue
    variable = E
    point = '0.04 0 0'
  []
  [E_x045]
    type = PointValue
    variable = E
    point = '0.045 0 0'
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
  nl_abs_tol = 1e-13
  nl_rel_tol = 1e-11
  nl_max_its = 20
  l_tol = 1e-13
  l_max_its = 500
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]

[Outputs]
  exodus = true
  csv = true
[]
