#!/usr/bin/env python3
"""Inject finite ion-induced secondary-electron emission into the generated Issue #395 FEM input.

Controlled discriminator parameters inherited from the accepted Issue #3 SEE path:
  gamma_SEE = 0.05
  emitted-electron energy = 4 eV

SEE is driven by positive-ion wall fluxes only:
  Gamma_SEE = gamma * (Gamma_O2+ + Gamma_O+)

Positive wall flux is outward from the plasma. SEE particle/energy terms are therefore
negative signed wall fluxes (inward to the plasma). Dielectric surface-current ledgers
receive +e*Gamma_SEE so charge bookkeeping remains closed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

SEE_GAMMA = 0.05
SEE_ENERGY_EV = 4.0
SOLID_BOUNDARIES = (
    "plasma_electrode plasma_metal plasma_right "
    "plasma_cover plasma_wafer plasma_focus_ring"
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def inject(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    if "property_name = see_number_flux" in text or "see_gamma" in text:
        raise RuntimeError("SEE already present; refusing duplicate injection")

    electron_wall_block = """  [electron_wall_flux]\n    type = PhysicsElectronWallFluxMaterial\n    electron_density = n_e_physical\n    mean_energy = mean_en_solved\n    sticking = 1.0\n    block = plasma\n  []\n"""

    see_materials = electron_wall_block + f"""  [secondary_electron_constants]\n    type = ADGenericFunctorMaterial\n    prop_names = 'see_gamma see_energy_eV'\n    prop_values = '{SEE_GAMMA:.17g} {SEE_ENERGY_EV:.17g}'\n    block = plasma\n  []\n  [secondary_electron_flux]\n    type = ADParsedFunctorMaterial\n    property_name = see_number_flux\n    functor_names = 'see_gamma ion_wall_number_flux atomic_positive_ion_wall_number_flux'\n    functor_symbols = 'g gi gop'\n    expression = 'g*(gi+gop)'\n    block = plasma\n  []\n  [secondary_electron_signed_particle_flux]\n    type = ADParsedFunctorMaterial\n    property_name = see_signed_particle_flux\n    functor_names = 'see_number_flux'\n    functor_symbols = 'gs'\n    expression = '-gs'\n    block = plasma\n  []\n  [secondary_electron_signed_energy_flux]\n    type = ADParsedFunctorMaterial\n    property_name = see_signed_energy_flux_eV\n    functor_names = 'see_number_flux see_energy_eV'\n    functor_symbols = 'gs eps'\n    expression = '-eps*gs'\n    block = plasma\n  []\n"""
    text = replace_once(text, electron_wall_block, see_materials, "electron-wall material anchor")

    for name, prop in (
        ("cover_surface_current", "cover_net_surface_current_density"),
        ("wafer_surface_current", "wafer_net_surface_current_density"),
        ("focus_ring_surface_current", "focus_ring_net_surface_current_density"),
    ):
        old = f"""  [{name}]\n    type = ADParsedFunctorMaterial\n    property_name = {prop}\n    functor_names = 'ion_wall_number_flux atomic_positive_ion_wall_number_flux negative_ion_wall_number_flux electron_wall_number_flux'\n    functor_symbols = 'gi gop gm ge'\n    expression = '1.602176634e-19*(gi+gop-gm-ge)'\n    block = plasma\n  []\n"""
        new = f"""  [{name}]\n    type = ADParsedFunctorMaterial\n    property_name = {prop}\n    functor_names = 'ion_wall_number_flux atomic_positive_ion_wall_number_flux negative_ion_wall_number_flux electron_wall_number_flux see_number_flux'\n    functor_symbols = 'gi gop gm ge gs'\n    expression = '1.602176634e-19*(gi+gop-gm-ge+gs)'\n    block = plasma\n  []\n"""
        text = replace_once(text, old, new, f"{name} SEE current closure")

    bcs_anchor = """[BCs]\n  [electron_sheath]\n"""
    see_bcs = f"""[BCs]\n  [secondary_electron_particle_source]\n    type = PhysicsFEMLogMolarDielectricFluxBC\n    variable = log_ne\n    signed_number_flux = see_signed_particle_flux\n    boundary = '{SOLID_BOUNDARIES}'\n  []\n  [secondary_electron_energy_source]\n    type = PhysicsFEMLogMolarDielectricFluxBC\n    variable = log_energy\n    signed_number_flux = see_signed_energy_flux_eV\n    boundary = '{SOLID_BOUNDARIES}'\n  []\n  [electron_sheath]\n"""
    text = replace_once(text, bcs_anchor, see_bcs, "BC section anchor")

    pp_anchor = """[Postprocessors]\n"""
    see_pp = f"""[Postprocessors]\n  [see_number_flux_integral]\n    type = ADSideIntegralFunctorPostprocessor\n    boundary = '{SOLID_BOUNDARIES}'\n    functor = see_number_flux\n    functor_argument = face\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [see_particle_source_integral]\n    type = ADSideIntegralFunctorPostprocessor\n    boundary = '{SOLID_BOUNDARIES}'\n    functor = see_signed_particle_flux\n    functor_argument = face\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n"""
    text = replace_once(text, pp_anchor, see_pp, "postprocessor section anchor")

    required = (
        "property_name = see_number_flux",
        "expression = 'g*(gi+gop)'",
        "prop_values = '0.050000000000000003 4'",
        "signed_number_flux = see_signed_particle_flux",
        "signed_number_flux = see_signed_energy_flux_eV",
        "expression = '1.602176634e-19*(gi+gop-gm-ge+gs)'",
        "[see_number_flux_integral]",
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise RuntimeError(f"SEE injection verification failed; missing: {missing}")

    path.write_text(text, encoding="utf-8")
    print(f"enabled SEE in {path}")
    print(f"gamma_SEE={SEE_GAMMA}")
    print(f"see_energy_eV={SEE_ENERGY_EV}")
    print("SEE drivers: O2+ + O+ wall fluxes")
    print(f"SEE boundaries: {SOLID_BOUNDARIES}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    inject(args.input)


if __name__ == "__main__":
    main()
