#!/usr/bin/env python3
"""Opt-in Reaction 411: e + O2(X) -> e + O2(ex1), 4.5 eV electronic excitation.

Gudmundsson et al. (2000), J. Phys. D 33 1323-1331, Table 3:
k_particle(Te) = 1.07e-15 exp(-3.43/Te) [m^3/s], Te [eV] in [1, 7].
Here O2(ex1) is not separately transported: use an effective electron-energy
loss, with zero net O2/O/electron-number source. Never merge this with the
6 eV 412 dissociation channel; that channel produces O atoms.
"""
from __future__ import annotations

import argparse
from pathlib import Path

M_O2 = 0.032
ENERGY_LOSS_EV = 4.5
PROGRESS = "R_O2_ex1_411"
ENERGY_SOURCE = "S_electron_energy_molar_411"

REQUIRED = (
    "property_name = n_e_physical",
    "mean_energy = mean_en_solved",
    "property_name = rho_neutral",
    "property_name = w_O2_constraint",
    "[log_energy]",
)


def build(base: str) -> str:
    missing = [x for x in REQUIRED if x not in base]
    if missing:
        raise ValueError(f"411 base-input capability audit failed: {missing}")
    if PROGRESS in base or ENERGY_SOURCE in base:
        raise ValueError("411 requires no inherited reaction progress or energy source")

    text = f"""# Reaction 411: e + O2 -> e + O2(ex1), 4.5 eV loss only.
# Gudmundsson et al. (2000) Table 3; DOI 10.1088/0022-3727/33/11/311.
# Maxwellian k_particle = 1.07e-15 exp(-3.43/Te) [m3/s], Te in 1-7 eV.
# One rate owner R_O2_ex1_411 [mol/(m3 s)]. No species or charge source.
[FunctorMaterials]
  [ei411_o2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2_411
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/{M_O2:.17g}'
    block = plasma
  []
  [ei411_progress]
    type = PhysicsElectronImpactO2Ex1ExcitationMaterial
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2_411
    mean_energy = mean_en_solved
    block = plasma
  []
  [ei411_energy_source]
    type = ADParsedFunctorMaterial
    property_name = {ENERGY_SOURCE}
    functor_names = '{PROGRESS}'
    functor_symbols = 'R'
    expression = '-{ENERGY_LOSS_EV:.17g}*R'
    block = plasma
  []
[]

[Kernels]
  [ei411_electron_energy_loss]
    type = FunctorKernel
    variable = log_energy
    functor = {ENERGY_SOURCE}
    functor_on_rhs = true
    block = plasma
  []
[]

[Postprocessors]
  [ei411_R_min]
    type = ADElementExtremeFunctorValue
    functor = {PROGRESS}
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei411_R_max]
    type = ADElementExtremeFunctorValue
    functor = {PROGRESS}
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei411_R_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = {PROGRESS}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei411_energy_loss_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = {ENERGY_SOURCE}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""
    if text.count("type = PhysicsElectronImpactO2Ex1ExcitationMaterial") != 1:
        raise AssertionError("411 requires exactly one kinetic progress owner")
    if text.count(f"functor_names = '{PROGRESS}'") != 1:
        raise AssertionError("411 energy must consume the single shared progress")
    for forbidden in (
        "[FVKernels]", "variable = w_O", "variable = p",
        "variable = log_ne", "R_diss_O2", "S_O_mass",
        "O2s_excitation_mass_source", "type = PhysicsElectronImpactRateMaterial"
    ):
        if forbidden in text:
            raise AssertionError(f"411 must be a formula-only energy channel: {forbidden}")
    return text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.write_text(build(a.base_input.read_text(encoding="utf-8")), encoding="utf-8")
    print("REACTION_411_O2_EX1_FORMULA_OVERLAY_BUILD_PASS")
    print(f"output={a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
