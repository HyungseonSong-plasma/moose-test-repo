#!/usr/bin/env python3
"""Generate isolated Issue #3 dielectric SEE electron-energy controls."""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent

W0 = 1.0e16
MEAN_E = 3.0
DT = 1.0e-7
CASES = {
    "see_off": 0.0,
    "see_on": 1.0e21,
}


def build(see_flux: float) -> str:
    return f'''# Issue #3 D4 isolated dielectric SEE energy control.
# Plasma is block 1 and dielectric is block 2. electron_energy exists only in plasma.
# The internal plasma_dielectric sideset is therefore a boundary of the FV energy domain.
# This discriminator isolates PhysicsFVElectronEnergyWallFluxBC from charge bookkeeping.
# SEE number flux is controlled directly: {see_flux:.17g} 1/(m^2 s).

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
[]

[Variables]
  [electron_energy]
    type = MooseVariableFVReal
    initial_condition = {W0:.17g}
    scaling = 1.0e-22
    block = 1
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_energy zero_diffusion see_number_flux'
    prop_values = '{MEAN_E:.17g} 0.0 {see_flux:.17g}'
    block = 1
  []
[]

[FVKernels]
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
[]

[FVBCs]
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

[Postprocessors]
  [energy_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = electron_energy
    block = 1
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {DT:.17g}
  end_time = {DT:.17g}
  nl_abs_tol = 1.0e-10
  nl_rel_tol = 1.0e-11
  nl_max_its = 30
  automatic_scaling = true
[]

[Outputs]
  csv = true
[]
'''


def main() -> None:
    for mode, see_flux in CASES.items():
        path = HERE / f"d4_see_energy_{mode}.i"
        path.write_text(build(see_flux), encoding="utf-8")
        print(f"wrote {path.name}: SEE flux={see_flux:.17g}")


if __name__ == "__main__":
    main()
