# Issue #3 D6 representative 2D integrated dielectric acceptance.
#
# Geometry (unit out-of-plane depth):
#   0 <= x <= 1 : plasma block 1
#   1 <= x <= 2 : dielectric block 2
#   0 <= y <= 2 : four interface segments
#
# Canonical coupling path under test:
#   FV charged species -> shared face fluxes -> particle loss / finite SEE
#                      -> net surface current -> lower-D sigma_s
#                      -> FEM Poisson surface source -> updated electrostatics
#                      -> ion migration contribution to the same wall flux
#
# gamma=0.05 and ion_mobility=1.0 are controlled verification parameters,
# not universal dielectric/material data.

[Mesh]
  [base]
    type = GeneratedMeshGenerator
    dim = 2
    xmin = 0
    xmax = 2
    ymin = 0
    ymax = 2
    nx = 2
    ny = 4
  []
  [plasma_block]
    type = SubdomainBoundingBoxGenerator
    input = base
    bottom_left = '-1 -1 -1'
    top_right = '1 3 1'
    block_id = 1
  []
  [dielectric_block]
    type = SubdomainBoundingBoxGenerator
    input = plasma_block
    bottom_left = '1 -1 -1'
    top_right = '3 3 1'
    block_id = 2
  []
  [plasma_dielectric_interface]
    type = SideSetsBetweenSubdomainsGenerator
    input = dielectric_block
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
  [log_ni]
    type = MooseVariableFVReal
    initial_condition = -27.123878827015126
    block = 1
  []
  [log_ne]
    type = MooseVariableFVReal
    initial_condition = -27.123878827015126
    block = 1
  []
  [potential]
    family = LAGRANGE
    order = FIRST
    initial_condition = 0
    block = '1 2'
  []
  [sigma_s]
    family = MONOMIAL
    order = CONSTANT
    initial_condition = 0
    block = 10
  []
[]

[FunctorMaterials]
  [plasma_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'ion_mobility T_g mean_energy zero_diffusion see_gamma'
    prop_values = '1.0 300.0 3.0 0.0 0.05'
    block = 1
  []
  [ion_density]
    type = ADParsedFunctorMaterial
    property_name = n_i_physical
    functor_names = 'log_ni'
    functor_symbols = 'ui'
    expression = '6.02214076e23*exp(ui)'
    block = 1
  []
  [electron_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'log_ne'
    functor_symbols = 'ue'
    expression = '6.02214076e23*exp(ue)'
    block = 1
  []
  [ion_wall_flux]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = n_i_physical
    potential = potential
    mobility = ion_mobility
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.032
    sticking = 1.0
    ion_temperature_eV = 0.0
    migration_gate_smoothing_width = 0.0
    use_element_gradient_for_potential = true
    block = 1
  []
  [electron_wall_flux]
    type = PhysicsElectronWallFluxMaterial
    electron_density = n_e_physical
    mean_energy = mean_energy
    sticking = 1.0
    block = 1
  []
  [see_flux]
    type = ADParsedFunctorMaterial
    property_name = see_number_flux
    functor_names = 'see_gamma ion_wall_number_flux'
    functor_symbols = 'g gi'
    expression = 'g*gi'
    block = 1
  []
  [signed_ion_flux]
    type = ADParsedFunctorMaterial
    property_name = signed_ion_number_flux
    functor_names = 'ion_wall_number_flux'
    functor_symbols = 'gi'
    expression = 'gi'
    block = 1
  []
  [signed_electron_flux]
    type = ADParsedFunctorMaterial
    property_name = signed_electron_number_flux
    functor_names = 'electron_wall_number_flux see_number_flux'
    functor_symbols = 'ge gs'
    expression = 'ge-gs'
    block = 1
  []
  [surface_current]
    type = ADParsedFunctorMaterial
    property_name = net_surface_current_density
    functor_names = 'signed_ion_number_flux signed_electron_number_flux'
    functor_symbols = 'gi ge'
    expression = '1.602176634e-19*(gi-ge)'
    block = 1
  []
  [see_current]
    type = ADParsedFunctorMaterial
    property_name = see_surface_current_density
    functor_names = 'see_number_flux'
    functor_symbols = 'gs'
    expression = '1.602176634e-19*gs'
    block = 1
  []
  [charge_density]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = 'n_i_physical n_e_physical'
    functor_symbols = 'ni ne'
    expression = '1.602176634e-19*(ni-ne)'
    block = 1
  []
  [poisson_source]
    type = ADParsedFunctorMaterial
    property_name = poisson_source
    functor_names = 'n_i_physical n_e_physical'
    functor_symbols = 'ni ne'
    expression = '1.8095128179727827e-08*(ni-ne)'
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
  [surface_material_anchor]
    type = ADGenericConstantMaterial
    prop_names = 'surface_material_anchor'
    prop_values = '0.0'
    block = 10
  []
[]

[FVKernels]
  [ion_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ni
    block = 1
  []
  [ion_zero_transport]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ni
    coeff = zero_diffusion
    block = 1
  []
  [electron_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ne
    block = 1
  []
  [electron_zero_transport]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ne
    coeff = zero_diffusion
    block = 1
  []
[]

[FVBCs]
  [ion_dielectric_flux]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_ni
    signed_number_flux = signed_ion_number_flux
    boundary = plasma_dielectric
  []
  [electron_dielectric_flux]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_ne
    signed_number_flux = signed_electron_number_flux
    boundary = plasma_dielectric
  []
[]

[Kernels]
  [potential_diffusion]
    type = ADMatDiffusion
    variable = potential
    diffusivity = relative_permittivity
    block = '1 2'
  []
  [potential_volume_charge]
    type = FunctorKernel
    variable = potential
    functor = poisson_source
    functor_on_rhs = true
    block = 1
  []
  [sigma_time]
    type = ADTimeDerivative
    variable = sigma_s
    block = 10
  []
  [sigma_surface_current]
    type = PhysicsLowerDSurfaceCurrent
    variable = sigma_s
    surface_current_density = net_surface_current_density
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
  [ion_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_i_physical
    block = 1
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e_physical
    block = 1
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [volume_charge]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density_C_m3
    block = 1
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [ion_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ion_surface_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = ion_surface_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ion_migration_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = ion_migration_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_primary_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = electron_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [see_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = see_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_signed_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = signed_electron_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [see_current]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = see_surface_current_density
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [net_surface_current]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = net_surface_current_density
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [surface_charge_total]
    type = ElementIntegralVariablePostprocessor
    variable = sigma_s
    block = 10
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sigma_average]
    type = ElementAverageValue
    variable = sigma_s
    block = 10
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sigma_min]
    type = ElementExtremeValue
    variable = sigma_s
    value_type = min
    block = 10
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sigma_max]
    type = ElementExtremeValue
    variable = sigma_s
    value_type = max
    block = 10
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [ion_density_min]
    type = ADElementExtremeFunctorValue
    functor = n_i_physical
    value_type = min
    block = 1
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ion_density_max]
    type = ADElementExtremeFunctorValue
    functor = n_i_physical
    value_type = max
    block = 1
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_density_min]
    type = ADElementExtremeFunctorValue
    functor = n_e_physical
    value_type = min
    block = 1
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_density_max]
    type = ADElementExtremeFunctorValue
    functor = n_e_physical
    value_type = max
    block = 1
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
  dt = 1.0e-9
  end_time = 5.0e-9
  nl_abs_tol = 1.0e-13
  nl_rel_tol = 1.0e-10
  nl_max_its = 40
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = true
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Outputs]
  csv = true
  exodus = true
[]
