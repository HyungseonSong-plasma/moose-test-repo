#!/usr/bin/env python3
"""Generate Issue #3 D4 zero/finite dielectric SEE control inputs."""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent

AVOGADRO = 6.02214076e23
INV_AVOGADRO = 1.0 / AVOGADRO
E_CHARGE = 1.602176634e-19
N_I0 = 1.0e16
N_E0 = 9414771885720.256
MEAN_ENERGY_EV = 3.0
ENERGY0 = N_E0 * MEAN_ENERGY_EV
DT = 1.0e-7

CASES = {
    "see_off": 0.0,
    "see_on": 0.05,
}


def build(gamma: float) -> str:
    return f'''# Issue #3 D4 dielectric SEE control.
# n points plasma -> dielectric. Positive wall number flux is outward from plasma.
# Gamma_SEE = gamma * Gamma_i is emitted from dielectric back into plasma.
# Therefore j_SEE,to_surface = +e*Gamma_SEE.
# gamma={gamma:.17g}; this is a controlled mechanism/sign coefficient inherited
# from the accepted oxygen-ICP SEE discriminator, not a universal dielectric value.

[Mesh]
  type = GeneratedMesh
  dim = 1
  xmin = 0
  xmax = 1
  nx = 1
[]

[Variables]
  [log_ni]
    type = MooseVariableFVReal
    initial_condition = -17.913538455038942
  []
  [log_ne]
    type = MooseVariableFVReal
    initial_condition = -24.8815988940131
  []
  [electron_energy]
    type = MooseVariableFVReal
    initial_condition = {ENERGY0:.17g}
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
    prop_values = '0.0 300.0 {MEAN_ENERGY_EV:.17g} 0.0 {gamma:.17g}'
    block = 0
  []

  [ion_density]
    type = ADParsedFunctorMaterial
    property_name = n_i_physical
    functor_names = 'log_ni'
    functor_symbols = 'ui'
    expression = '{AVOGADRO:.17g}*exp(ui)'
    block = 0
  []

  [electron_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'log_ne'
    functor_symbols = 'ue'
    expression = '{AVOGADRO:.17g}*exp(ue)'
    block = 0
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
    block = 0
  []

  [electron_wall_flux]
    type = PhysicsElectronWallFluxMaterial
    electron_density = n_e_physical
    mean_energy = mean_energy
    sticking = 1.0
    block = 0
  []

  [see_flux]
    type = ADParsedFunctorMaterial
    property_name = see_number_flux
    functor_names = 'see_gamma ion_wall_number_flux'
    functor_symbols = 'g gi'
    expression = 'g*gi'
    block = 0
  []

  [ion_surface_current]
    type = ADParsedFunctorMaterial
    property_name = ion_surface_current_density
    functor_names = 'ion_wall_number_flux'
    functor_symbols = 'gi'
    expression = '{E_CHARGE:.17g}*gi'
    block = 0
  []

  [electron_surface_current]
    type = ADParsedFunctorMaterial
    property_name = electron_surface_current_density
    functor_names = 'electron_wall_number_flux'
    functor_symbols = 'ge'
    expression = '-{E_CHARGE:.17g}*ge'
    block = 0
  []

  [see_surface_current]
    type = ADParsedFunctorMaterial
    property_name = see_surface_current_density
    functor_names = 'see_number_flux'
    functor_symbols = 'gs'
    expression = '{E_CHARGE:.17g}*gs'
    block = 0
  []

  [net_surface_current]
    type = ADParsedFunctorMaterial
    property_name = net_surface_current_density
    functor_names = 'ion_surface_current_density electron_surface_current_density see_surface_current_density'
    functor_symbols = 'ji je js'
    expression = 'ji+je+js'
    block = 0
  []

  [volume_charge_density]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = 'n_i_physical n_e_physical'
    functor_symbols = 'ni ne'
    expression = '{E_CHARGE:.17g}*(ni-ne)'
    block = 0
  []
[]

[FVKernels]
  [ion_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ni
  []
  [ion_zero_transport]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ni
    coeff = zero_diffusion
  []
  [electron_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ne
  []
  [electron_zero_transport]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ne
    coeff = zero_diffusion
  []
  [energy_time]
    type = FVTimeKernel
    variable = electron_energy
  []
  [energy_zero_transport]
    type = FVDiffusion
    variable = electron_energy
    coeff = zero_diffusion
  []
[]

[FVBCs]
  [ion_dielectric_loss]
    type = FVFunctorNeumannBC
    variable = log_ni
    functor = ion_wall_number_flux
    factor = {-INV_AVOGADRO:.17g}
    boundary = right
  []
  [electron_primary_loss]
    type = FVFunctorNeumannBC
    variable = log_ne
    functor = electron_wall_number_flux
    factor = {-INV_AVOGADRO:.17g}
    boundary = right
  []
  [electron_see_source]
    type = FVFunctorNeumannBC
    variable = log_ne
    functor = see_number_flux
    factor = {INV_AVOGADRO:.17g}
    boundary = right
  []
  [electron_energy_wall]
    type = PhysicsFVElectronEnergyWallFluxBC
    variable = electron_energy
    boundary = right
    electron_energy_density = electron_energy
    mean_electron_energy = mean_energy
    see_number_flux = see_number_flux
    state_form = physical_eV
  []
[]

[UserObjects]
  [surface_charge_state]
    type = PhysicsSurfaceChargeState
    boundary = right
    surface_current_density = net_surface_current_density
    initial_surface_charge = 0
    execute_on = TIMESTEP_END
  []
[]

[Postprocessors]
  [ion_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_i_physical
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e_physical
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [energy_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = electron_energy
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [volume_charge]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density_C_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [ion_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = ion_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [electron_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = electron_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [see_number_flux_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = see_number_flux
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [see_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = see_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []
  [net_current_integral]
    type = ADSideIntegralFunctorPostprocessor
    boundary = right
    functor = net_surface_current_density
    functor_argument = face
    execute_on = TIMESTEP_END
  []

  [surface_total_charge]
    type = PhysicsSurfaceChargeStatePostprocessor
    surface_charge_state = surface_charge_state
    quantity = total_charge
    execute_on = TIMESTEP_END
  []
  [surface_area]
    type = PhysicsSurfaceChargeStatePostprocessor
    surface_charge_state = surface_charge_state
    quantity = surface_area
    execute_on = TIMESTEP_END
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
        path = HERE / f"d4_{mode}.i"
        path.write_text(build(gamma), encoding="utf-8")
        print(f"wrote {path.name}: gamma={gamma}")


if __name__ == "__main__":
    main()
