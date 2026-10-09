# Issue #3 redesigned D5 discriminator.
#
# Canonical coupling:
#   higher-D FV face current j_to_surface
#        -> lower-D nonlinear sigma_s
#        -> continuous FEM Poisson surface source
#
# Geometry is two 1 m cells:
#   x in [0,1]  : plasma, epsilon_r = 1
#   x in [1,2]  : dielectric, epsilon_r = 4
# with phi(0)=phi(2)=0 and one internal plasma-dielectric sideset.
#
# A controlled face current j=1e-4 A/m^2 is used for this first architecture
# discriminator.  With dt=1e-7 s,
#   sigma_s = 1e-11 C/m^2.
# The normalized Poisson weak form is
#   -div(epsilon_r grad(phi)) = rho/epsilon_0
# with an internal surface source sigma_s/epsilon_0, so for unit layer lengths
#   phi_interface = sigma_s / (epsilon_0*(1+4)).

[Mesh]
  [base]
    type = GeneratedMeshGenerator
    dim = 1
    xmin = 0
    xmax = 2
    nx = 2
    subdomain_ids = '1 2'
  []
  [plasma_dielectric_interface]
    type = SideSetsBetweenSubdomainsGenerator
    input = base
    primary_block = 1
    paired_block = 2
    new_boundary = plasma_dielectric
  []
  [surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = plasma_dielectric_interface
    sidesets = plasma_dielectric
    new_block_id = 10
    new_block_name = dielectric_surface
  []
[]

[Variables]
  [potential]
    family = LAGRANGE
    order = FIRST
    block = '1 2'
    initial_condition = 0
  []
  [sigma_s]
    family = MONOMIAL
    order = CONSTANT
    block = 10
    initial_condition = 0
  []
[]

# The FV anchor forces FaceInfo construction on the plasma cell.  The next
# discriminator replaces the controlled current with the actual charged-species
# wall-current functors evaluated on this same higher-D face.
[AuxVariables]
  [fv_face_info_anchor]
    type = MooseVariableFVReal
    block = 1
  []
[]

[FunctorMaterials]
  [controlled_surface_current]
    type = ADGenericFunctorMaterial
    prop_names = 'surface_current_density'
    prop_values = '1.0e-4'
    block = 1
  []
[]

[Materials]
  [eps_plasma]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '1.0'
    block = 1
  []
  [eps_dielectric]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '4.0'
    block = 2
  []
  # MOOSE requires every mesh block to own at least one active Material once
  # any Material object is present.  sigma_s itself does not consume this.
  [surface_material_anchor]
    type = ADGenericConstantMaterial
    prop_names = 'surface_material_anchor'
    prop_values = '0.0'
    block = 10
  []
[]

[Kernels]
  [potential_diffusion]
    type = ADMatDiffusion
    variable = potential
    diffusivity = relative_permittivity
    block = '1 2'
  []

  [sigma_time]
    type = ADTimeDerivative
    variable = sigma_s
    block = 10
  []
  [sigma_surface_current]
    type = PhysicsLowerDSurfaceCurrent
    variable = sigma_s
    surface_current_density = surface_current_density
    block = 10
  []
[]

[BCs]
  [left_ground]
    type = DirichletBC
    variable = potential
    boundary = left
    value = 0
  []
  [right_ground]
    type = DirichletBC
    variable = potential
    boundary = right
    value = 0
  []
  [surface_charge_poisson]
    type = PhysicsADSurfaceChargePoissonBC
    variable = potential
    boundary = plasma_dielectric
    surface_charge = sigma_s
  []
[]

[Postprocessors]
  [sigma_average]
    type = ElementAverageValue
    variable = sigma_s
    block = 10
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_interface]
    type = SideAverageValue
    variable = potential
    boundary = plasma_dielectric
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 1.0e-7
  end_time = 1.0e-7
  nl_abs_tol = 1.0e-13
  nl_rel_tol = 1.0e-11
  nl_max_its = 30
[]

[Outputs]
  csv = true
[]
