#!/usr/bin/env python3
from pathlib import Path

HERE = Path(__file__).resolve().parent

DT = 1.0e-9
NSTEPS = 100
END_TIME = DT * NSTEPS
NE0 = 1.0e15
NI0 = 1.0e15
MEAN_E0 = 4.0
WE0 = NE0 * MEAN_E0
PRESSURE = 1.333223684
TG = 300.0
ION_MU = 10.0
ION_D = 0.25851999786435537

GROUND = "inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring"
EWALL = "plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring"

MESH = r'''[Mesh]
  coord_type = RZ
  rz_coord_axis = Y

  [main]
    type = FileMeshGenerator
    file = '../Issue91_real_qvt_r3/r3_e0/qvt.msh'
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
[]
'''

COMMON_MATERIALS = f'''[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'p_fixed T_g_fixed ion_mobility ion_diffusion carrier_one relative_permittivity'
    prop_values = '{PRESSURE:.12g} {TG:.12g} {ION_MU:.12g} {ION_D:.17g} 1.0 1.0'
    block = plasma
  []
  [mean_energy]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = electron_energy
    electron_density = n_e
    state_form = physical_eV
    block = plasma
  []
  [electron_transport]
    type = PhysicsElectronTransportLookupMaterial
    property_table_file = '../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'
    mean_energy = mean_en_solved
    pressure = p_fixed
    gas_temperature = T_g_fixed
    bounds_policy = clamp
    block = plasma
  []
  [charge_number_density]
    type = ADParsedFunctorMaterial
    property_name = charge_number_density
    functor_names = 'n_i n_e'
    functor_symbols = 'ni ne'
    expression = 'ni-ne'
    block = plasma
  []
  [poisson_source]
    type = ADParsedFunctorMaterial
    property_name = poisson_source
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.8095128179727827e-08*nq'
    block = plasma
  []
  [ion_wall_flux]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = n_i
    potential = potential
    mobility = ion_mobility
    gas_temperature = T_g_fixed
    charge_number = 1
    molar_mass = 0.032
    sticking = 1.0
    ion_temperature_eV = 0.0
    migration_gate_smoothing_width = 1.0e-3
    block = plasma
  []
[]
'''

COMMON_PP = '''[Postprocessors]
  [ne_min]
    type = ElementExtremeFunctorValue
    functor = n_e
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ne_max]
    type = ElementExtremeFunctorValue
    functor = n_e
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ni_min]
    type = ElementExtremeFunctorValue
    functor = n_i
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ni_max]
    type = ElementExtremeFunctorValue
    functor = n_i
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_min]
    type = ElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_max]
    type = ElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_min]
    type = ElementExtremeFunctorValue
    functor = potential
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_max]
    type = ElementExtremeFunctorValue
    functor = potential
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_integral]
    type = ElementIntegralFunctorPostprocessor
    functor = charge_number_density
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
'''

EXEC = f'''[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {DT:.17g}
  num_steps = {NSTEPS}
  end_time = {END_TIME:.17g}
  line_search = bt
  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-10
  nl_max_its = 100
  l_tol = 1e-10
  l_max_its = 20
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = false
  petsc_options = '-snes_converged_reason'
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
  exodus = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
'''


def fem():
    return MESH + f'''
[Variables]
  [n_e]
    family = LAGRANGE
    order = FIRST
    initial_condition = {NE0:.17g}
    block = plasma
  []
  [n_i]
    family = LAGRANGE
    order = FIRST
    initial_condition = {NI0:.17g}
    block = plasma
  []
  [electron_energy]
    family = LAGRANGE
    order = FIRST
    initial_condition = {WE0:.17g}
    block = plasma
  []
  [potential]
    family = LAGRANGE
    order = FIRST
    initial_condition = 0.0
    block = plasma
  []
[]

''' + COMMON_MATERIALS + f'''
[Kernels]
  [ne_time]
    type = ADTimeDerivative
    variable = n_e
    block = plasma
  []
  [ne_transport]
    type = PhysicsFEMPlasmaDriftDiffusion
    variable = n_e
    potential = potential
    mobility = electron_mobility
    diffusion = electron_diffusion
    charge_number = -1
    block = plasma
  []
  [ni_time]
    type = ADTimeDerivative
    variable = n_i
    block = plasma
  []
  [ni_transport]
    type = PhysicsFEMPlasmaDriftDiffusion
    variable = n_i
    potential = potential
    mobility = ion_mobility
    diffusion = ion_diffusion
    charge_number = 1
    block = plasma
  []
  [energy_time]
    type = ADTimeDerivative
    variable = electron_energy
    block = plasma
  []
  [energy_transport]
    type = PhysicsFEMPlasmaDriftDiffusion
    variable = electron_energy
    potential = potential
    mobility = electron_energy_mobility
    diffusion = electron_energy_diffusion
    charge_number = -1
    block = plasma
  []
  [energy_joule]
    type = PhysicsFEMElectronJouleHeating
    variable = electron_energy
    electron_density = n_e
    potential = potential
    mobility = electron_mobility
    diffusion = electron_diffusion
    block = plasma
  []
  [phi_diffusion]
    type = ADDiffusion
    variable = potential
    block = plasma
  []
  [phi_source]
    type = FunctorKernel
    variable = potential
    functor = poisson_source
    functor_on_rhs = true
    block = plasma
  []
[]

[BCs]
  [electron_sheath]
    type = PhysicsFEMElectronGroundedSheathBC
    variable = n_e
    electron_energy_density = electron_energy
    potential = potential
    boundary = '{EWALL}'
  []
  [electron_energy_sheath]
    type = PhysicsFEMElectronGroundedSheathEnergyBC
    variable = electron_energy
    electron_density = n_e
    potential = potential
    boundary = '{EWALL}'
  []
  [ion_wall]
    type = PhysicsFEMIonWallBC
    variable = n_i
    potential = potential
    mobility = {ION_MU:.17g}
    gas_temperature = {TG:.17g}
    molar_mass = 0.032
    charge_number = 1
    sticking = 1.0
    migration_gate_smoothing_width = 1.0e-3
    boundary = '{GROUND}'
  []
  [grounded_potential]
    type = DirichletBC
    variable = potential
    value = 0.0
    boundary = '{GROUND}'
  []
[]

''' + COMMON_PP + EXEC


def fvm():
    return MESH + f'''
[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = {NE0:.17g}
    block = plasma
  []
  [n_i]
    type = MooseVariableFVReal
    initial_condition = {NI0:.17g}
    block = plasma
  []
  [electron_energy]
    type = MooseVariableFVReal
    initial_condition = {WE0:.17g}
    block = plasma
  []
  [potential]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
[]

''' + COMMON_MATERIALS + f'''
[FVKernels]
  [ne_time]
    type = FVTimeKernel
    variable = n_e
    block = plasma
  []
  [ne_diffusion]
    type = FVDiffusion
    variable = n_e
    coeff = electron_diffusion
    block = plasma
  []
  [ne_drift]
    type = PhysicsFVElectrostaticDrift
    variable = n_e
    potential = potential
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = '{GROUND}'
    block = plasma
  []
  [ni_time]
    type = FVTimeKernel
    variable = n_i
    block = plasma
  []
  [ni_diffusion]
    type = FVDiffusion
    variable = n_i
    coeff = ion_diffusion
    block = plasma
  []
  [ni_drift]
    type = PhysicsFVElectrostaticDrift
    variable = n_i
    potential = potential
    mobility = ion_mobility
    carrier = carrier_one
    charge_number = 1
    advected_interp_method = upwind
    boundaries_to_avoid = '{GROUND}'
    block = plasma
  []
  [energy_time]
    type = FVTimeKernel
    variable = electron_energy
    block = plasma
  []
  [energy_diffusion]
    type = FVDiffusion
    variable = electron_energy
    coeff = electron_energy_diffusion
    block = plasma
  []
  [energy_drift]
    type = PhysicsFVElectrostaticDrift
    variable = electron_energy
    potential = potential
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = '{GROUND}'
    block = plasma
  []
  [energy_joule]
    type = PhysicsFVElectronEnergyJouleHeating
    variable = electron_energy
    electron_density = n_e
    potential = potential
    mobility = electron_mobility
    diffusion = electron_diffusion
    state_form = physical_eV
    block = plasma
  []
  [phi_diffusion]
    type = FVDiffusion
    variable = potential
    coeff = relative_permittivity
    block = plasma
  []
  [phi_source]
    type = FVCoupledForce
    variable = potential
    v = poisson_source
    coef = 1.0
    block = plasma
  []
[]

[FVBCs]
  [electron_sheath]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = n_e
    mean_electron_energy = mean_en_solved
    potential = potential
    boundary = '{EWALL}'
  []
  [electron_energy_sheath]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = electron_energy
    electron_density = n_e
    mean_electron_energy = mean_en_solved
    potential = potential
    physical_eV_state = true
    boundary = '{EWALL}'
  []
  [ion_wall]
    type = FVFunctorNeumannBC
    variable = n_i
    functor = ion_wall_number_flux
    factor = -1.0
    boundary = '{GROUND}'
  []
  [grounded_potential]
    type = FVDirichletBC
    variable = potential
    value = 0.0
    boundary = '{GROUND}'
  []
[]

''' + COMMON_PP + EXEC


if __name__ == '__main__':
    cases = {
        'fem': fem(),
        'fvm': fvm(),
    }
    for name, text in cases.items():
        path = HERE / f'{name}_plasma_discriminator.i'
        path.write_text(text, encoding='utf-8')
        print(f'wrote {path}')
    print(f'dt={DT} s; steps={NSTEPS}; end_time={END_TIME} s')
    print(f'initial ne=ni={NE0} 1/m3; initial mean electron energy={MEAN_E0} eV')
    print(f'fixed ion mu={ION_MU} m2/(V s); fixed ion D={ION_D} m2/s at 300 K discriminator')
    print('chemistry=OFF; heavy flow=OFF; wall-layer Joule suppression=OFF')
