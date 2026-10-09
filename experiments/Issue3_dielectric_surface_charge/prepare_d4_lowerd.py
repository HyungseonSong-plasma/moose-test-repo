#!/usr/bin/env python3
"""Generate lower-D Issue #3 D4 zero/finite dielectric SEE controls."""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent

NA = 6.02214076e23
E = 1.602176634e-19
N_I0 = 1.0e16
N_E0 = 9414771885720.256
MEAN_E = 3.0
ENERGY0 = N_E0 * MEAN_E
DT = 1.0e-7

CASES = {"see_off": 0.0, "see_on": 0.05}


def build(gamma: float) -> str:
    return f'''# Issue #3 D4 lower-D dielectric SEE control.
# One internal plasma-dielectric interface; species exist only in plasma.
# Electron signed outward flux = primary absorption - emitted SEE.
# gamma={gamma:.17g} is a controlled mechanism/sign coefficient, not a
# universal dielectric material value. SEE emission energy is 4 eV.
# The dielectric-anchor FV reaction exists only to satisfy MOOSE kernel
# coverage in this D4 mechanism test; D5 separately validates the real FEM
# dielectric Poisson equation and sigma_s electrostatic feedback.

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
    initial_condition = -17.913538455038942
    block = 1
  []
  [log_ne]
    type = MooseVariableFVReal
    initial_condition = -24.8815988940131
    block = 1
  []
  [electron_energy]
    type = MooseVariableFVReal
    initial_condition = {ENERGY0:.17g}
    scaling = 1.0e-25
    block = 1
  []
  [dielectric_anchor]
    type = MooseVariableFVReal
    initial_condition = 0
    block = 2
  []
  [sigma_s]
    family = MONOMIAL
    order = CONSTANT
    initial_condition = 0
    block = 10
  []
[]

[Functions]
  [zero_potential]
    type = ParsedFunction
    expression = '0'
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
    potential = zero_potential
    mobility = ion_mobility
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.032
    sticking = 1.0
    ion_temperature_eV = 0.0
    migration_gate_smoothing_width = 0.0
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
  [ion_current]
    type = ADParsedFunctorMaterial
    property_name = ion_surface_current_density
    functor_names = 'signed_ion_number_flux'
    functor_symbols = 'gi'
    expression = '{E:.17g}*gi'
    block = 1
  []
  [primary_electron_current]
    type = ADParsedFunctorMaterial
    property_name = primary_electron_surface_current_density
    functor_names = 'electron_wall_number_flux'
    functor_symbols = 'ge'
    expression = '-{E:.17g}*ge'
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
  [energy_time]
    type = FVTimeKernel
    variable = electron_energy
    block = 1
  []
  [energy_zero_transport]
    type = FVDiffusion
    variable = electron_energy
    coeff = zero_diffusion
    block = 1
  []
  [dielectric_anchor_reaction]
    type = FVReaction
    variable = dielectric_anchor
    rate = 1.0
    block = 2
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
  [electron_energy_dielectric_flux]
    type = PhysicsFVElectronEnergyWallFluxBC
    variable = electron_energy
    boundary = plasma_dielectric
    electron_energy_density = electron_energy
    mean_electron_energy = mean_energy
    see_number_flux = see_number_flux
    state_form = physical_eV
  []
[]

[Kernels]
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
  [energy_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = electron_energy
    block = 1
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [volume_charge]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density_C_m3
    block = 1
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ion_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = ion_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [electron_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = primary_electron_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [see_number_flux_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = see_number_flux
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [see_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = see_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [net_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_dielectric
    functor = net_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [surface_charge]
    type = ElementAverageValue
    variable = sigma_s
    block = 10
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {DT:.17g}
  end_time = {DT:.17g}
  nl_abs_tol = 1.0e-11
  nl_rel_tol = 1.0e-10
  nl_max_its = 40
[]

[Outputs]
  csv = true
[]
'''


def main() -> None:
    for mode, gamma in CASES.items():
        path = HERE / f"d4_lowerd_{mode}.i"
        path.write_text(build(gamma), encoding="utf-8")
        print(f"wrote {path.name}: gamma={gamma}")


if __name__ == "__main__":
    main()
