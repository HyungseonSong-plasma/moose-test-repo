#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib
from pathlib import Path

SOURCE_SHA256 = 'b267457a9d8e54290f9d20dd1d7c5e84bf7a4851a6831c6a0ef9b18693a25b1e'

FULL_MESH = r'''[Mesh]
  coord_type = RZ
  rz_coord_axis = Y

  [main]
    type = FileMeshGenerator
    file = '../Issue19_sccm_pressure_boundary/qvt.msh'
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
  [wafer_electrode_ground]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = wafer
    paired_block = electrode
    new_boundary = wafer_electrode_ground
    input = plasma_focus_ring
  []
  [focus_electrode_ground]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = focus_ring
    paired_block = electrode
    new_boundary = focus_electrode_ground
    input = wafer_electrode_ground
  []
  [cover_surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = focus_electrode_ground
    sidesets = plasma_cover
    new_block_id = 130
    new_block_name = cover_surface
  []
  [wafer_surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = cover_surface_block
    sidesets = plasma_wafer
    new_block_id = 131
    new_block_name = wafer_surface
  []
  [focus_surface_block]
    type = LowerDBlockFromSidesetGenerator
    input = wafer_surface_block
    sidesets = plasma_focus_ring
    new_block_id = 132
    new_block_name = focus_surface
  []
[]
'''


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f'{label}: expected one match, found {n}')
    return text.replace(old, new, 1)


def replace_block(text: str, section_start: str, next_section: str, new: str) -> str:
    start = text.index(section_start)
    end = text.index(next_section, start)
    return text[:start] + new.rstrip() + '\n\n' + text[end:]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('input', type=Path)
    args = ap.parse_args()
    text = args.input.read_text()
    if sha(text) != SOURCE_SHA256:
        raise RuntimeError(f'unexpected finalized cover pilot sha256={sha(text)}')

    text = text.replace('# Issue #3 practical baseline dielectric pilot', '# Issue #3 full-geometry practical dielectric pilot', 1)
    text = text.replace('# Cover relative permittivity eps_r=3.6 follows the original QVT geometry/material provenance.\n# SEE is disabled in this first practical pilot; cover bulk-conductivity leakage is not yet modeled.',
                        '# Full qvt.msh geometry: cover eps_r=3.6, wafer eps_r=12.5, focus ring eps_r=8.\n# Electrode is excluded from the Poisson domain; all dielectric/electrode contacts are grounded at phi=0.\n# SEE is disabled in this structural pilot; dielectric bulk leakage is not yet modeled.', 1)

    text = replace_block(text, '[Mesh]\n', '[GlobalParams]\n', FULL_MESH)

    text = replace_once(text,
'''  [potential]\n    family = LAGRANGE\n    order = FIRST\n    initial_condition = 0.0\n    block = 'plasma cover'\n  []\n  [sigma_s]\n    family = MONOMIAL\n    order = CONSTANT\n    initial_condition = 0.0\n    block = cover_surface\n  []''',
'''  [potential]\n    family = LAGRANGE\n    order = FIRST\n    initial_condition = 0.0\n    block = 'plasma cover wafer focus_ring'\n  []\n  [sigma_s]\n    family = MONOMIAL\n    order = CONSTANT\n    initial_condition = 0.0\n    block = cover_surface\n  []\n  [sigma_wafer]\n    family = MONOMIAL\n    order = CONSTANT\n    initial_condition = 0.0\n    block = wafer_surface\n  []\n  [sigma_focus]\n    family = MONOMIAL\n    order = CONSTANT\n    initial_condition = 0.0\n    block = focus_surface\n  []''', 'variables')

    text = replace_once(text,
'''  [eps_cover]\n    type = ADGenericConstantMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '3.6'\n    block = cover\n  []\n  [cover_surface_anchor]\n    type = ADGenericConstantMaterial\n    prop_names = 'cover_surface_anchor'\n    prop_values = '0.0'\n    block = cover_surface\n  []''',
'''  [eps_cover]\n    type = ADGenericConstantMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '3.6'\n    block = cover\n  []\n  [eps_wafer]\n    type = ADGenericConstantMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '12.5'\n    block = wafer\n  []\n  [eps_focus]\n    type = ADGenericConstantMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '8.0'\n    block = focus_ring\n  []\n  [cover_surface_anchor]\n    type = ADGenericConstantMaterial\n    prop_names = 'cover_surface_anchor'\n    prop_values = '0.0'\n    block = cover_surface\n  []\n  [wafer_surface_anchor]\n    type = ADGenericConstantMaterial\n    prop_names = 'wafer_surface_anchor'\n    prop_values = '0.0'\n    block = wafer_surface\n  []\n  [focus_surface_anchor]\n    type = ADGenericConstantMaterial\n    prop_names = 'focus_surface_anchor'\n    prop_values = '0.0'\n    block = focus_surface\n  []''', 'materials')

    text = replace_once(text,
'''  [phi_diffusion]\n    type = ADMatDiffusion\n    variable = potential\n    diffusivity = relative_permittivity\n    block = 'plasma cover'\n  []''',
'''  [phi_diffusion]\n    type = ADMatDiffusion\n    variable = potential\n    diffusivity = relative_permittivity\n    block = 'plasma cover wafer focus_ring'\n  []''', 'phi_diffusion')

    text = replace_once(text,
'''  [sigma_surface_current]\n    type = PhysicsLowerDSurfaceCurrent\n    variable = sigma_s\n    surface_current_density = cover_net_surface_current_density\n    block = cover_surface\n  []''',
'''  [sigma_surface_current]\n    type = PhysicsLowerDSurfaceCurrent\n    variable = sigma_s\n    surface_current_density = cover_net_surface_current_density\n    block = cover_surface\n  []\n  [sigma_wafer_time]\n    type = ADTimeDerivative\n    variable = sigma_wafer\n    block = wafer_surface\n  []\n  [sigma_wafer_surface_current]\n    type = PhysicsLowerDSurfaceCurrent\n    variable = sigma_wafer\n    surface_current_density = cover_net_surface_current_density\n    block = wafer_surface\n  []\n  [sigma_focus_time]\n    type = ADTimeDerivative\n    variable = sigma_focus\n    block = focus_surface\n  []\n  [sigma_focus_surface_current]\n    type = PhysicsLowerDSurfaceCurrent\n    variable = sigma_focus\n    surface_current_density = cover_net_surface_current_density\n    block = focus_surface\n  []''', 'surface kernels')

    text = text.replace("boundary = 'plasma_electrode plasma_metal plasma_right plasma_wafer plasma_focus_ring'", "boundary = 'plasma_electrode plasma_metal plasma_right'", 2)

    old_heavy = "boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_wafer plasma_focus_ring'"
    new_heavy = "boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right'"
    if text.count(old_heavy) < 3:
        raise RuntimeError(f'charged-heavy wall BCs: expected at least three matches, found {text.count(old_heavy)}')
    text = text.replace(old_heavy, new_heavy, 3)

    text = replace_once(text,
'''  [electron_cover_dielectric]\n    type = PhysicsFEMLogMolarDielectricFluxBC\n    variable = log_ne\n    signed_number_flux = electron_wall_number_flux\n    boundary = plasma_cover\n  []''',
'''  [electron_cover_dielectric]\n    type = PhysicsFEMLogMolarDielectricFluxBC\n    variable = log_ne\n    signed_number_flux = electron_wall_number_flux\n    boundary = plasma_cover\n  []\n  [electron_wafer_dielectric]\n    type = PhysicsFEMLogMolarDielectricFluxBC\n    variable = log_ne\n    signed_number_flux = electron_wall_number_flux\n    boundary = plasma_wafer\n  []\n  [electron_focus_dielectric]\n    type = PhysicsFEMLogMolarDielectricFluxBC\n    variable = log_ne\n    signed_number_flux = electron_wall_number_flux\n    boundary = plasma_focus_ring\n  []''', 'electron dielectric BCs')

    text = replace_once(text,
'''  [electron_energy_cover]\n    type = PhysicsFEMLogMolarElectronEnergyDielectricBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = plasma_cover\n  []''',
'''  [electron_energy_cover]\n    type = PhysicsFEMLogMolarElectronEnergyDielectricBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = plasma_cover\n  []\n  [electron_energy_wafer]\n    type = PhysicsFEMLogMolarElectronEnergyDielectricBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = plasma_wafer\n  []\n  [electron_energy_focus]\n    type = PhysicsFEMLogMolarElectronEnergyDielectricBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = plasma_focus_ring\n  []''', 'energy dielectric BCs')

    text = replace_once(text,
"    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_wafer plasma_focus_ring cover_outer_ground cover_outer_right'",
"    boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right wafer_electrode_ground focus_electrode_ground'", 'ground BC')

    text = replace_once(text,
'''  [cover_surface_charge_poisson]\n    type = PhysicsADSurfaceChargePoissonBC\n    variable = potential\n    boundary = plasma_cover\n    surface_charge = sigma_s\n  []''',
'''  [cover_surface_charge_poisson]\n    type = PhysicsADSurfaceChargePoissonBC\n    variable = potential\n    boundary = plasma_cover\n    surface_charge = sigma_s\n  []\n  [wafer_surface_charge_poisson]\n    type = PhysicsADSurfaceChargePoissonBC\n    variable = potential\n    boundary = plasma_wafer\n    surface_charge = sigma_wafer\n  []\n  [focus_surface_charge_poisson]\n    type = PhysicsADSurfaceChargePoissonBC\n    variable = potential\n    boundary = plasma_focus_ring\n    surface_charge = sigma_focus\n  []''', 'poisson surface BCs')

    for species_name, variable, functor in [
        ('ion', 'log_ni', 'ion_wall_number_flux'),
        ('negative_ion', 'log_nm', 'negative_ion_wall_number_flux'),
        ('atomic_positive_ion', 'log_nop', 'atomic_positive_ion_wall_number_flux')]:
        marker = f'''  [{species_name}_cover_dielectric]\n    type = PhysicsFVLogMolarDielectricFluxBC\n    variable = {variable}\n    signed_number_flux = {functor}\n    boundary = plasma_cover\n  []'''
        addition = marker + f'''\n  [{species_name}_wafer_dielectric]\n    type = PhysicsFVLogMolarDielectricFluxBC\n    variable = {variable}\n    signed_number_flux = {functor}\n    boundary = plasma_wafer\n  []\n  [{species_name}_focus_dielectric]\n    type = PhysicsFVLogMolarDielectricFluxBC\n    variable = {variable}\n    signed_number_flux = {functor}\n    boundary = plasma_focus_ring\n  []'''
        text = replace_once(text, marker, addition, f'{species_name} dielectric BCs')

    insert_before = '''  [neutral_mass_total]\n'''
    extra_pp = '''  [wafer_net_surface_current]\n    type = ADSideIntegralFunctorPostprocessor\n    boundary = plasma_wafer\n    functor = cover_net_surface_current_density\n    functor_argument = face\n    execute_on = 'INITIAL TIMESTEP_END'\n    restrict_to_functors_domain = true\n  []\n  [wafer_surface_charge_total]\n    type = ElementIntegralVariablePostprocessor\n    variable = sigma_wafer\n    block = wafer_surface\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [wafer_sigma_average]\n    type = ElementAverageValue\n    variable = sigma_wafer\n    block = wafer_surface\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [wafer_interface_potential]\n    type = SideAverageValue\n    variable = potential\n    boundary = plasma_wafer\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [focus_net_surface_current]\n    type = ADSideIntegralFunctorPostprocessor\n    boundary = plasma_focus_ring\n    functor = cover_net_surface_current_density\n    functor_argument = face\n    execute_on = 'INITIAL TIMESTEP_END'\n    restrict_to_functors_domain = true\n  []\n  [focus_surface_charge_total]\n    type = ElementIntegralVariablePostprocessor\n    variable = sigma_focus\n    block = focus_surface\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [focus_sigma_average]\n    type = ElementAverageValue\n    variable = sigma_focus\n    block = focus_surface\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [focus_interface_potential]\n    type = SideAverageValue\n    variable = potential\n    boundary = plasma_focus_ring\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n\n'''
    text = replace_once(text, insert_before, extra_pp + insert_before, 'full dielectric diagnostics')

    args.input.write_text(text)
    print(f'FULL_DIELECTRIC_EXPANSION_PASS source_sha256={SOURCE_SHA256} final_sha256={sha(text)}')

if __name__ == '__main__':
    main()
