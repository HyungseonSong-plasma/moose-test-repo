#!/usr/bin/env python3
"""Generate isolated Issue #3 dielectric SEE electron-energy controls."""

from __future__ import annotations

import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

NA = 6.02214076e23
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
# This discriminator isolates the log-molar wall-energy balance from charge bookkeeping.
# SEE number flux is controlled directly: {see_flux:.17g} 1/(m^2 s).
# dielectric_anchor and dielectric_material_anchor exist only to satisfy MOOSE
# whole-mesh integrity checks; neither is coupled to electron_energy.

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
    initial_condition = {math.log(W0/NA):.17g}
    scaling = {NA*1.0e-22:.17g}
    block = 1
  []
  [dielectric_anchor]
    type = MooseVariableFVReal
    initial_condition = 0
    block = 2
  []
[]

[FunctorMaterials]
  [physical_energy_readback]
    type = ADParsedFunctorMaterial
    property_name = reconstructed_energy
    functor_names = 'electron_energy'
    functor_symbols = 'u'
    expression = '{NA:.17g}*exp(u)'
    block = 1
  []
  [electron_energy_dielectric_flux_outward_energy_flux]
    type = ADParsedFunctorMaterial
    property_name = electron_energy_dielectric_flux_outward_energy_flux
    functor_names = 'electron_energy mean_energy see_number_flux'
    functor_symbols = 'w eps gs'
    expression = '(5.0/6.0)*sqrt(16.0*1.6021766339999999e-19*eps/(3.0*3.141592653589793238462643383279502884*9.1093837138999998e-31))*exp(w)-4*gs/{NA:.17g}'
    block = 1
  []
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_energy zero_diffusion see_number_flux'
    prop_values = '{MEAN_E:.17g} 0.0 {see_flux:.17g}'
    block = 1
  []
  [dielectric_material_anchor]
    type = ADGenericFunctorMaterial
    prop_names = 'dielectric_material_anchor'
    prop_values = '0.0'
    block = 2
  []
[]

[FVKernels]
  [energy_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = electron_energy
    block = 1
  []
  [energy_zero_transport]
    type = PhysicsFVLogMolarElectronDiffusion
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
  [electron_energy_dielectric_flux]
    type = FVFunctorNeumannBC
    variable = electron_energy
    boundary = plasma_dielectric
    functor = electron_energy_dielectric_flux_outward_energy_flux
    factor = -1
  []
[]

[Postprocessors]
  [energy_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = reconstructed_energy
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
