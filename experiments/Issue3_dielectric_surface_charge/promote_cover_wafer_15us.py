#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    args = ap.parse_args()
    text = args.input.read_text(encoding="utf-8")

    old_mesh = """[Mesh]
  coord_type = RZ
  rz_coord_axis = Y
  [main]
    type = FileMeshGenerator
    file = 'baseline_cover_dielectric.msh'
  []
  [plasma_cover_owner]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = cover
    new_boundary = plasma_cover_owner
    input = main
  []
  [cover_surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = plasma_cover_owner
    sidesets = plasma_cover_owner
    new_block_id = 30
    new_block_name = cover_surface
  []
[]"""
    new_mesh = """[Mesh]
  coord_type = RZ
  rz_coord_axis = Y
  [main]
    type = FileMeshGenerator
    file = 'baseline_plasma_plus_unstructured_cover_plus_wafer.msh'
  []
  [plasma_cover_owner]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = cover
    new_boundary = plasma_cover_owner
    input = main
  []
  [plasma_wafer_owner]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = wafer
    new_boundary = plasma_wafer_owner
    input = plasma_cover_owner
  []
  [cover_surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = plasma_wafer_owner
    sidesets = plasma_cover_owner
    new_block_id = 30
    new_block_name = cover_surface
  []
  [wafer_surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = cover_surface_block
    sidesets = plasma_wafer_owner
    new_block_id = 31
    new_block_name = wafer_surface
  []
[]"""
    text = replace_once(text, old_mesh, new_mesh, "mesh")

    text = replace_once(text, "    block = 'plasma cover'\n  []\n  [sigma_s]", "    block = 'plasma cover wafer'\n  []\n  [sigma_s]", "potential block")
    sigma = """  [sigma_s]
    family = MONOMIAL
    order = CONSTANT
    initial_condition = 0.0
    block = cover_surface
  []"""
    text = replace_once(text, sigma, sigma + """
  [sigma_wafer]
    family = MONOMIAL
    order = CONSTANT
    initial_condition = 0.0
    block = wafer_surface
  []""", "wafer sigma variable")

    cover_current = """  [cover_surface_current]
    type = ADParsedFunctorMaterial
    property_name = cover_net_surface_current_density
    functor_names = 'ion_wall_number_flux atomic_positive_ion_wall_number_flux negative_ion_wall_number_flux electron_wall_number_flux'
    functor_symbols = 'gi gop gm ge'
    expression = '1.602176634e-19*(gi+gop-gm-ge)'
    block = plasma
  []"""
    text = replace_once(text, cover_current, cover_current + """
  [wafer_surface_current]
    type = ADParsedFunctorMaterial
    property_name = wafer_net_surface_current_density
    functor_names = 'ion_wall_number_flux atomic_positive_ion_wall_number_flux negative_ion_wall_number_flux electron_wall_number_flux'
    functor_symbols = 'gi gop gm ge'
    expression = '1.602176634e-19*(gi+gop-gm-ge)'
    block = plasma
  []""", "wafer surface current")

    materials = """  [eps_cover]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '3.6'
    block = cover
  []
  [cover_surface_anchor]
    type = ADGenericConstantMaterial
    prop_names = 'cover_surface_anchor'
    prop_values = '0.0'
    block = cover_surface
  []"""
    text = replace_once(text, materials, """  [eps_cover]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '3.6'
    block = cover
  []
  [eps_wafer]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '12.5'
    block = wafer
  []
  [cover_surface_anchor]
    type = ADGenericConstantMaterial
    prop_names = 'cover_surface_anchor'
    prop_values = '0.0'
    block = cover_surface
  []
  [wafer_surface_anchor]
    type = ADGenericConstantMaterial
    prop_names = 'wafer_surface_anchor'
    prop_values = '0.0'
    block = wafer_surface
  []""", "wafer materials")

    text = replace_once(text, "    block = 'plasma cover'\n  []\n  [phi_source]", "    block = 'plasma cover wafer'\n  []\n  [phi_source]", "phi diffusion")

    sigma_kernels = """  [sigma_time]
    type = ADTimeDerivative
    variable = sigma_s
    block = cover_surface
  []
  [sigma_surface_current]
    type = PhysicsLowerDSurfaceCurrent
    variable = sigma_s
    surface_current_density = cover_net_surface_current_density
    block = cover_surface
  []"""
    text = replace_once(text, sigma_kernels, sigma_kernels + """
  [sigma_wafer_time]
    type = ADTimeDerivative
    variable = sigma_wafer
    block = wafer_surface
  []
  [sigma_wafer_surface_current]
    type = PhysicsLowerDSurfaceCurrent
    variable = sigma_wafer
    surface_current_density = wafer_net_surface_current_density
    block = wafer_surface
  []""", "wafer surface kernels")

    for name in ("electron_sheath", "electron_energy_sheath"):
        old = block(text, name)
        new = old.replace(" plasma_wafer", "")
        if new == old:
            raise RuntimeError(f"{name}: plasma_wafer was not present")
        text = replace_once(text, old, new, name)

    electron_cover = """  [electron_cover_dielectric]
    type = PhysicsFEMLogMolarDielectricFluxBC
    variable = log_ne
    signed_number_flux = electron_wall_number_flux
    boundary = plasma_cover
  []"""
    text = replace_once(text, electron_cover, electron_cover + """
  [electron_wafer_dielectric]
    type = PhysicsFEMLogMolarDielectricFluxBC
    variable = log_ne
    signed_number_flux = electron_wall_number_flux
    boundary = plasma_wafer
  []""", "electron wafer dielectric")

    energy_cover = """  [electron_energy_cover]
    type = PhysicsFEMLogMolarElectronEnergyDielectricBC
    variable = log_energy
    log_electron_density = log_ne
    boundary = plasma_cover
  []"""
    text = replace_once(text, energy_cover, energy_cover + """
  [electron_energy_wafer]
    type = PhysicsFEMLogMolarElectronEnergyDielectricBC
    variable = log_energy
    log_electron_density = log_ne
    boundary = plasma_wafer
  []""", "electron energy wafer dielectric")

    ground = block(text, "grounded_potential")
    ground_new = ground.replace(" plasma_wafer", "").replace(" cover_outer_right'", " cover_outer_right wafer_electrode'")
    text = replace_once(text, ground, ground_new, "wafer electrode ground")

    cover_poisson = """  [cover_surface_charge_poisson]
    type = PhysicsADSurfaceChargePoissonBC
    variable = potential
    boundary = plasma_cover
    surface_charge = sigma_s
  []"""
    text = replace_once(text, cover_poisson, cover_poisson + """
  [wafer_surface_charge_poisson]
    type = PhysicsADSurfaceChargePoissonBC
    variable = potential
    boundary = plasma_wafer
    surface_charge = sigma_wafer
  []""", "wafer surface charge Poisson")

    for name in ("ion_wall", "negative_ion_wall", "atomic_positive_ion_wall"):
        old = block(text, name)
        new = old.replace(" plasma_wafer", "")
        if new == old:
            raise RuntimeError(f"{name}: plasma_wafer was not present")
        text = replace_once(text, old, new, name)

    cover_fv = """  [ion_cover_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_ni
    signed_number_flux = ion_wall_number_flux
    boundary = plasma_cover
  []
  [negative_ion_cover_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nm
    signed_number_flux = negative_ion_wall_number_flux
    boundary = plasma_cover
  []
  [atomic_positive_ion_cover_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nop
    signed_number_flux = atomic_positive_ion_wall_number_flux
    boundary = plasma_cover
  []"""
    text = replace_once(text, cover_fv, cover_fv + """
  [ion_wafer_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_ni
    signed_number_flux = ion_wall_number_flux
    boundary = plasma_wafer
  []
  [negative_ion_wafer_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nm
    signed_number_flux = negative_ion_wall_number_flux
    boundary = plasma_wafer
  []
  [atomic_positive_ion_wafer_dielectric]
    type = PhysicsFVLogMolarDielectricFluxBC
    variable = log_nop
    signed_number_flux = atomic_positive_ion_wall_number_flux
    boundary = plasma_wafer
  []""", "wafer charged-heavy dielectric BCs")

    cover_pp = """  [cover_interface_potential]
    type = SideAverageValue
    variable = potential
    boundary = plasma_cover
    execute_on = 'INITIAL TIMESTEP_END'
  []"""
    wafer_pp = """
  [wafer_net_surface_current]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_wafer
    functor = wafer_net_surface_current_density
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [wafer_electron_primary_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_wafer
    functor = electron_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [wafer_O2p_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_wafer
    functor = ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [wafer_Om_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_wafer
    functor = negative_ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [wafer_Op_flux]
    type = ADSideIntegralFunctorPostprocessor
    boundary = plasma_wafer
    functor = atomic_positive_ion_wall_number_flux
    functor_argument = face
    execute_on = 'INITIAL TIMESTEP_END'
    restrict_to_functors_domain = true
  []
  [wafer_surface_charge_total]
    type = ElementIntegralVariablePostprocessor
    variable = sigma_wafer
    block = wafer_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_sigma_average]
    type = ElementAverageValue
    variable = sigma_wafer
    block = wafer_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_sigma_min]
    type = ElementExtremeValue
    variable = sigma_wafer
    value_type = min
    block = wafer_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_sigma_max]
    type = ElementExtremeValue
    variable = sigma_wafer
    value_type = max
    block = wafer_surface
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_interface_potential]
    type = SideAverageValue
    variable = potential
    boundary = plasma_wafer
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wafer_ground_potential]
    type = SideAverageValue
    variable = potential
    boundary = wafer_electrode
    execute_on = 'INITIAL TIMESTEP_END'
  []"""
    text = replace_once(text, cover_pp, cover_pp + wafer_pp, "wafer diagnostics")

    ground_final = block(text, "grounded_potential")
    if "plasma_wafer" in ground_final or "wafer_electrode" not in ground_final:
        raise RuntimeError("wafer ground routing is incorrect")
    if "plasma_wafer" in block(text, "electron_energy_sheath"):
        raise RuntimeError("generic energy BC still owns plasma_wafer")
    if text.count("type = PhysicsFEMLogMolarElectronEnergyDielectricBC") != 2:
        raise RuntimeError("expected cover+wafer dielectric energy BCs")
    if text.count("type = PhysicsLowerDSurfaceCurrent") != 2:
        raise RuntimeError("expected cover+wafer lower-D surface-current kernels")
    if text.count("type = PhysicsADSurfaceChargePoissonBC") != 2:
        raise RuntimeError("expected cover+wafer surface-charge Poisson BCs")

    args.input.write_text(text, encoding="utf-8")
    print("COVER_WAFER_15US_PROMOTION_PASS wafer_eps_r=12.5 wafer_surface_charge=true wafer_electrode_ground_V=0 baseline_energy_wall_law_preserved=true bulk_conductivity_leakage=false")


if __name__ == "__main__":
    main()
