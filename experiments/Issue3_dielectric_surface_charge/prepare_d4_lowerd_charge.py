#!/usr/bin/env python3
"""Generate compact lower-D dielectric SEE charge/particle controls for Issue #3."""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent

NA = 6.02214076e23
E = 1.602176634e-19
N0 = 1.0e12
LOG_C0 = -27.123878827015126
DT = 1.0e-9
MEAN_E = 3.0

CASES = {"see_off": 0.0, "see_on": 0.05}


def build(gamma: float) -> str:
    return f'''# Issue #3 D4 lower-D dielectric SEE charge/particle control.
# One physical internal plasma-dielectric interface.
# Species exist only in the plasma block; potential spans plasma+dielectric.
# Electron signed outward particle flux is Gamma_primary - Gamma_SEE.
# gamma={gamma:.17g} is a controlled verification coefficient.

[Mesh]
  [base]
    type = GeneratedMeshGenerator
    dim = 1
    xmin = 0
    xmax = 2
    nx = 2
    subdomain_ids = '1 2'
  []
  [interface]
    type = SideSetsBetweenSubdomainsGenerator
    input = base
    primary_block = 1
    paired_block = 2
    new_boundary = plasma_dielectric
  []
  [surface]
    type = LowerDBlockFromSidesetGenerator
    input = interface
    sidesets = plasma_dielectric
    new_block_id = 10
    new_block_name = dielectric_surface
  []
[]

[Variables]
  [log_ni]
    type = MooseVariableFVReal
    initial_condition = {LOG_C0:.17g}
    block = 1
  []
  [log_ne]
    type = MooseVariableFVReal
    initial_condition = {LOG_C0:.17g}
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
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'ion_mobility T_g mean_energy zero_diffusion see_gamma'
    prop_values = '0.0 300.0 {MEAN_E:.17g} 0.0 {gamma:.17g}'
    block = 1
  []
  [ion_density]
    type = ADParsedFunctorMaterial
    property_name = n_i_physical
    functor_names = 'log_ni'
    functor_symbols = 'ui'
    expression = '{NA:.17g}*exp(ui)'
    block = 1
  []
  [electron_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'log_ne'
    functor_symbols = 'ue'
    expression = '{NA:.17g}*exp(ue)'
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
    expression = '{E:.17g}*(gi-ge)'
    block = 1
  []
  [see_current]
    type = ADParsedFunctorMaterial
    property_name = see_surface_current_density
    functor_names = 'see_number_flux'
    functor_symbols = 'gs'
    expression = '{E:.17g}*gs'
    block = 1
  []
  [charge_density]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = 'n_i_physical n_e_physical'
    functor_symbols = 'ni ne'
    expression = '{E:.17g}*(ni-ne)'
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
  [see_number_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = see_number_flux
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [see_current]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = see_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [net_surface_current]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = net_surface_current_density
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [surface_charge]
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
  dt = {DT:.17g}
  end_time = {DT:.17g}
  nl_abs_tol = 1.0e-13
  nl_rel_tol = 1.0e-11
  nl_max_its = 40
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Outputs]
  csv = true
[]
'''


def main() -> None:
    for mode, gamma in CASES.items():
        path = HERE / f"d4_lowerd_charge_{mode}.i"
        path.write_text(build(gamma), encoding="utf-8")
        print(f"wrote {path.name}: gamma={gamma}")


if __name__ == "__main__":
    main()
