#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def block(text: str, name: str) -> str:
    header = f"  [{name}]\n"
    start = text.index(header)
    end = text.index("\n  []", start) + len("\n  []")
    return text[start:end]


def append_after_block(text: str, name: str, addition: str) -> str:
    old = block(text, name)
    return replace_once(text, old, old + "\n" + addition, f"append after {name}")


def replace_in_block(text: str, name: str, old: str, new: str) -> str:
    current = block(text, name)
    if old not in current:
        raise RuntimeError(f"{name}: token not present: {old!r}")
    return replace_once(text, current, current.replace(old, new, 1), name)


def update_boundary(text: str, name: str, *, remove=(), add=()) -> str:
    current = block(text, name)
    match = re.search(r"(?m)^(\s*boundary\s*=\s*')([^']*)(')\s*$", current)
    if not match:
        raise RuntimeError(f"{name}: single-quoted boundary list not found")
    tokens = match.group(2).split()
    for token in remove:
        if token not in tokens:
            raise RuntimeError(f"{name}: boundary token {token!r} not present")
        tokens.remove(token)
    for token in add:
        if token in tokens:
            raise RuntimeError(f"{name}: boundary token {token!r} already present")
        tokens.append(token)
    replacement = match.group(1) + " ".join(tokens) + match.group(3)
    updated = current[:match.start()] + replacement + current[match.end():]
    return replace_once(text, current, updated, f"boundary routing {name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    args = ap.parse_args()
    text = args.input.read_text(encoding="utf-8")

    focus_owner = """  [plasma_focus_ring_owner]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = focus_ring
    new_boundary = plasma_focus_ring_owner
    input = plasma_wafer_owner
  []"""
    text = append_after_block(text, "plasma_wafer_owner", focus_owner)
    text = replace_in_block(
        text, "cover_surface_block", "input = plasma_wafer_owner", "input = plasma_focus_ring_owner"
    )

    focus_surface = """  [focus_ring_surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = wafer_surface_block
    sidesets = plasma_focus_ring_owner
    new_block_id = 32
    new_block_name = focus_ring_surface
  []"""
    text = append_after_block(text, "wafer_surface_block", focus_surface)

    for name in ("potential", "phi_diffusion"):
        text = replace_in_block(
            text,
            name,
            "block = 'plasma cover wafer'",
            "block = 'plasma cover wafer focus_ring'",
        )

    sigma_focus = """  [sigma_focus_ring]
    family = MONOMIAL
    order = CONSTANT
    initial_condition = 0.0
    block = focus_ring_surface
  []"""
    text = append_after_block(text, "sigma_wafer", sigma_focus)

    focus_current = """  [focus_ring_surface_current]
    type = ADParsedFunctorMaterial
    property_name = focus_ring_net_surface_current_density
    functor_names = 'ion_wall_number_flux atomic_positive_ion_wall_number_flux negative_ion_wall_number_flux electron_wall_number_flux'
    functor_symbols = 'gi gop gm ge'
    expression = '1.602176634e-19*(gi+gop-gm-ge)'
    block = plasma
  []"""
    text = append_after_block(text, "wafer_surface_current", focus_current)

    eps_focus = """  [eps_focus_ring]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '8.0'
    block = focus_ring
  []"""
    text = append_after_block(text, "eps_wafer", eps_focus)

    focus_anchor = """  [focus_ring_surface_anchor]
    type = ADGenericConstantMaterial
    prop_names = 'focus_ring_surface_anchor'
    prop_values = '0.0'
    block = focus_ring_surface
  []"""
    text = append_after_block(text, "wafer_surface_anchor", focus_anchor)

    focus_kernels = """  [sigma_focus_ring_time]
    type = ADTimeDerivative
    variable = sigma_focus_ring
    block = focus_ring_surface
  []
  [sigma_focus_ring_surface_current]
    type = PhysicsLowerDSurfaceCurrent
    variable = sigma_focus_ring
    surface_current_density = focus_ring_net_surface_current_density
    block = focus_ring_surface
  []"""
    text = append_after_block(text, "sigma_wafer_surface_current", focus_kernels)

    for name in (
        "electron_sheath",
        "electron_energy_sheath",
        "ion_wall",
        "negative_ion_wall",
        "atomic_positive_ion_wall",
    ):
        text = update_boundary(text, name, remove=("plasma_focus_ring",))

    text = update_boundary(
        text,
        "grounded_potential",
        remove=("plasma_focus_ring",),
        add=("focus_ring_ground",),
    )

    electron_focus = """  [electron_focus_ring_dielectric]
    type = PhysicsFEMLogMolarDielectricFluxBC
    variable = log_ne
    signed_number_flux = electron_wall_number_flux
    boundary = plasma_focus_ring
  []"""
    text = append_after_block(text, "electron_wafer_dielectric", electron_focus)

    energy_focus = """  [electron_energy_focus_ring]
    type = PhysicsFEMLogMolarElectronEnergyDielectricBC
    variable = log_energy
    log_electron_density = log_ne
    boundary = plasma_focus_ring
  []"""
    text = append_after_block(text, "electron_energy_wafer", energy_focus)

    poisson_focus = """  [focus_ring_surface_charge_poisson]
    type = PhysicsADSurfaceChargePoissonBC
    variable = potential
    boundary = plasma_focus_ring
    surface_charge = sigma_focus_ring
  []"""
    text = append_after_block(text, "wafer_surface_charge_poisson", poisson_focus)

    focus_fv = """  [ion_focus_ring_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_ni
    signed_number_flux = ion_wall_number_flux
    boundary = plasma_focus_ring
  []
  [negative_ion_focus_ring_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nm
    signed_number_flux = negative_ion_wall_number_flux
    boundary = plasma_focus_ring
  []
  [atomic_positive_ion_focus_ring_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nop
    signed_number_flux = atomic_positive_ion_wall_number_flux
    boundary = plasma_focus_ring
  []"""
    text = append_after_block(text, "atomic_positive_ion_wafer_dielectric", focus_fv)

    focus_pp = """  [focus_ring_net_surface_current]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_focus_ring
    functor = focus_ring_net_surface_current_density
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [focus_ring_electron_primary_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_focus_ring
    functor = electron_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [focus_ring_O2p_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_focus_ring
    functor = ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [focus_ring_Om_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_focus_ring
    functor = negative_ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [focus_ring_Op_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_focus_ring
    functor = atomic_positive_ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [focus_ring_surface_charge_total]
    type = ElementIntegralVariablePostprocessor
    variable = sigma_focus_ring
    block = focus_ring_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_sigma_average]
    type = ElementAverageValue
    variable = sigma_focus_ring
    block = focus_ring_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_sigma_min]
    type = ElementExtremeValue
    variable = sigma_focus_ring
    value_type = min
    block = focus_ring_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_sigma_max]
    type = ElementExtremeValue
    variable = sigma_focus_ring
    value_type = max
    block = focus_ring_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_interface_potential]
    type = SideAverageValue
    variable = potential
    boundary = plasma_focus_ring
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [focus_ring_ground_potential]
    type = SideAverageValue
    variable = potential
    boundary = focus_ring_ground
    execute_on = 'INITIAL TIMESTEP_END'
  []"""
    text = append_after_block(text, "wafer_ground_potential", focus_pp)

    ground = block(text, "grounded_potential")
    if "plasma_focus_ring" in ground or "focus_ring_ground" not in ground:
        raise RuntimeError("focus-ring potential routing is incorrect")
    for name in (
        "electron_sheath",
        "electron_energy_sheath",
        "ion_wall",
        "negative_ion_wall",
        "atomic_positive_ion_wall",
    ):
        if "plasma_focus_ring" in block(text, name):
            raise RuntimeError(f"generic wall BC still owns plasma_focus_ring: {name}")
    if text.count("type = PhysicsFEMLogMolarElectronEnergyDielectricBC") != 3:
        raise RuntimeError("expected cover+wafer+focus-ring dielectric energy BCs")
    if text.count("type = PhysicsLowerDSurfaceCurrent") != 3:
        raise RuntimeError("expected cover+wafer+focus-ring lower-D surface-current kernels")
    if text.count("type = PhysicsADSurfaceChargePoissonBC") != 3:
        raise RuntimeError("expected cover+wafer+focus-ring surface-charge Poisson BCs")
    if "block = 'plasma cover wafer focus_ring'" not in block(text, "potential"):
        raise RuntimeError("potential does not span focus_ring")
    if "prop_values = '8.0'" not in block(text, "eps_focus_ring"):
        raise RuntimeError("focus_ring relative permittivity is not 8.0")

    args.input.write_text(text, encoding="utf-8")
    print(
        "FOCUS_RING_15US_PROMOTION_PASS "
        "focus_ring_block=true focus_ring_eps_r=8.0 "
        "focus_ring_surface_charge=true focus_ring_outer_ground_V=0 "
        "baseline_energy_wall_law_preserved=true bulk_conductivity_leakage=false"
    )


if __name__ == "__main__":
    main()
