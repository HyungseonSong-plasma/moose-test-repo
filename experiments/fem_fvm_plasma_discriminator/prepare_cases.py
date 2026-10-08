#!/usr/bin/env python3
from pathlib import Path
import math

HERE = Path(__file__).resolve().parent

NA = 6.02214076e23
DT = 1.0e-9
NSTEPS = 100
END_TIME = DT * NSTEPS

NE0 = 1.0e15
NI0 = 1.0e15
MEAN_E0 = 4.0

CE0 = NE0 / NA
CI0 = NI0 / NA
WE_MOLAR0 = CE0 * MEAN_E0
LOG_NE0 = math.log(CE0)
LOG_NI0 = math.log(CI0)
LOG_ENERGY0 = math.log(WE_MOLAR0)

PRESSURE = 1.333223684
TG = 300.0
ION_MU = 10.0
ION_D = 0.25851999786435537
INV_NA = 1.0 / NA

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
  [electron_molar_density]
    type = ADParsedFunctorMaterial
    property_name = electron_molar_density
    functor_names = 'log_ne'
    functor_symbols = 'u'
    expression = 'exp(u)'
    block = plasma
  []
  [ion_molar_density]
    type = ADParsedFunctorMaterial
    property_name = ion_molar_density
    functor_names = 'log_ni'
    functor_symbols = 'u'
    expression = 'exp(u)'
    block = plasma
  []
  [electron_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'electron_molar_density'
    functor_symbols = 'ce'
    expression = '6.02214076e23*ce'
    block = plasma
  []
  [ion_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_i_physical
    functor_names = 'ion_molar_density'
    functor_symbols = 'ci'
    expression = '6.02214076e23*ci'
    block = plasma
  []
  [electron_molar_energy_density]
    type = ADParsedFunctorMaterial
    property_name = electron_molar_energy_density
    functor_names = 'log_energy'
    functor_symbols = 'ue'
    expression = 'exp(ue)'
    block = plasma
  []
  [electron_physical_energy_density]
    type = ADParsedFunctorMaterial
    property_name = electron_energy_density_eV_m3
    functor_names = 'electron_molar_energy_density'
    functor_symbols = 'we'
    expression = '6.02214076e23*we'
    block = plasma
  []
  [mean_energy]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = log_energy
    electron_density = log_ne
    state_form = log_molar_eV
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
    functor_names = 'n_i_physical n_e_physical'
    functor_symbols = 'ni ne'
    expression = 'ni-ne'
    block = plasma
  []
  [charge_density]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.602176634e-19*nq'
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
    ion_number_density = n_i_physical
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
    type = ADElementExtremeFunctorValue
    functor = n_e_physical
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ne_max]
    type = ADElementExtremeFunctorValue
    functor = n_e_physical
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ni_min]
    type = ADElementExtremeFunctorValue
    functor = n_i_physical
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ni_max]
    type = ADElementExtremeFunctorValue
    functor = n_i_physical
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_min]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_max]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_min]
    type = ADElementExtremeFunctorValue
    functor = potential
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_max]
    type = ADElementExtremeFunctorValue
    functor = potential
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density_C_m3
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
  petsc_options = '-snes_converged_reason -ksp_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
  petsc_options_value = 'preonly lu NONZERO'
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
  [log_ne]
    family = LAGRANGE
    order = FIRST
    initial_condition = {LOG_NE0:.17g}
    block = plasma
  []
  [log_ni]
    family = LAGRANGE
    order = FIRST
    initial_condition = {LOG_NI0:.17g}
    block = plasma
  []
  [log_energy]
    family = LAGRANGE
    order = FIRST
    initial_condition = {LOG_ENERGY0:.17g}
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
    type = PhysicsFEMLogMolarTimeDerivative
    variable = log_ne
    block = plasma
  []
  [ne_transport]
    type = PhysicsFEMLogMolarDriftDiffusion
    variable = log_ne
    potential = potential
    mobility = electron_mobility
    diffusion = electron_diffusion
    charge_number = -1
    block = plasma
  []
  [ni_time]
    type = PhysicsFEMLogMolarTimeDerivative
    variable = log_ni
    block = plasma
  []
  [ni_transport]
    type = PhysicsFEMLogMolarDriftDiffusion
    variable = log_ni
    potential = potential
    mobility = ion_mobility
    diffusion = ion_diffusion
    charge_number = 1
    block = plasma
  []
  [energy_time]
    type = PhysicsFEMLogMolarTimeDerivative
    variable = log_energy
    block = plasma
  []
  [energy_transport]
    type = PhysicsFEMLogMolarDriftDiffusion
    variable = log_energy
    potential = potential
    mobility = electron_energy_mobility
    diffusion = electron_energy_diffusion
    charge_number = -1
    block = plasma
  []
  [energy_joule]
    type = PhysicsFEMLogMolarElectronJouleHeating
    variable = log_energy
    electron_log_density = log_ne
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
    type = PhysicsFEMLogMolarElectronGroundedSheathBC
    variable = log_ne
    log_energy = log_energy
    potential = potential
    boundary = '{EWALL}'
  []
  [electron_energy_sheath]
    type = PhysicsFEMLogMolarElectronGroundedSheathEnergyBC
    variable = log_energy
    log_electron_density = log_ne
    potential = potential
    boundary = '{EWALL}'
  []
  [ion_wall]
    type = PhysicsFEMLogMolarIonWallBC
    variable = log_ni
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
  [log_ne]
    type = MooseVariableFVReal
    initial_condition = {LOG_NE0:.17g}
    block = plasma
  []
  [log_ni]
    type = MooseVariableFVReal
    initial_condition = {LOG_NI0:.17g}
    block = plasma
  []
  [log_energy]
    type = MooseVariableFVReal
    initial_condition = {LOG_ENERGY0:.17g}
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
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ne
    block = plasma
  []
  [ne_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ne
    coeff = electron_diffusion
    block = plasma
  []
  [ne_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_ne
    potential = potential
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = '{GROUND}'
    block = plasma
  []
  [ni_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ni
    block = plasma
  []
  [ni_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ni
    coeff = ion_diffusion
    block = plasma
  []
  [ni_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_ni
    potential = potential
    mobility = ion_mobility
    carrier = carrier_one
    charge_number = 1
    advected_interp_method = upwind
    boundaries_to_avoid = '{GROUND}'
    block = plasma
  []
  [energy_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_energy
    block = plasma
  []
  [energy_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_energy
    coeff = electron_energy_diffusion
    block = plasma
  []
  [energy_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_energy
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
    variable = log_energy
    electron_density = electron_molar_density
    potential = potential
    mobility = electron_mobility
    diffusion = electron_diffusion
    state_form = molar_eV
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
    variable = log_ne
    mean_electron_energy = mean_en_solved
    potential = potential
    log_molar_state = true
    boundary = '{EWALL}'
  []
  [electron_energy_sheath]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = log_energy
    electron_density = electron_molar_density
    mean_electron_energy = mean_en_solved
    potential = potential
    molar_energy_state = true
    boundary = '{EWALL}'
  []
  [ion_wall]
    type = FVFunctorNeumannBC
    variable = log_ni
    functor = ion_wall_number_flux
    factor = {-INV_NA:.17g}
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

    print('state representation: identical log-molar electron, O2+, and electron-energy states')
    print(f'dt={DT} s; steps={NSTEPS}; end_time={END_TIME} s')
    print(f'initial ne=ni={NE0} 1/m3; initial mean electron energy={MEAN_E0} eV')
    print(f'initial log_ne={LOG_NE0:.17g}; log_ni={LOG_NI0:.17g}; log_energy={LOG_ENERGY0:.17g}')
    print(f'fixed ion mu={ION_MU} m2/(V s); fixed ion D={ION_D} m2/s at 300 K discriminator')
    print('electron transport=energy-dependent lookup; chemistry=OFF; heavy flow=OFF; wall-layer Joule suppression=OFF')
