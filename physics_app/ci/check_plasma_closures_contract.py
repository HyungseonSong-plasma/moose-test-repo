#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

required = [
    ROOT / "include/materials/ElectronClosureMaterial.h",
    ROOT / "src/materials/ElectronClosureMaterial.C",
    ROOT / "include/materials/PhysicsElectronImpactRateMaterial.h",
    ROOT / "src/materials/PhysicsElectronImpactRateMaterial.C",
    ROOT / "include/materials/PhysicsThermalDiffusionMaterial.h",
    ROOT / "src/materials/PhysicsThermalDiffusionMaterial.C",
    ROOT / "include/materials/PhysicsPlasmaChargeDensityMaterial.h",
    ROOT / "src/materials/PhysicsPlasmaChargeDensityMaterial.C",
]
for path in required:
    assert path.is_file(), path

app = (ROOT / "src/base/PhysicsApp.C").read_text()
assert 'PlasmaClosuresAction' not in app
assert 'PlasmaClosures/*' not in app
assert not (ROOT / "include/actions/PlasmaClosuresAction.h").exists()
assert not (ROOT / "src/actions/PlasmaClosuresAction.C").exists()
electron = (ROOT / "src/materials/ElectronClosureMaterial.C").read_text()
single_ei = (ROOT / "src/materials/PhysicsElectronImpactRateMaterial.C").read_text()
heavy = (ROOT / "src/materials/PhysicsThermalDiffusionMaterial.C").read_text()

# The unused composition wrapper and its two dedicated Material classes are retired.
# Keep existing registered physics implementations, not generated C++ sources.
for old_type in ("PhysicsElectronKineticsMaterial", "PhysicsHeavyTransportMaterial"):
    assert not (ROOT / "src/materials" / (old_type + ".C")).exists()
    assert not (ROOT / "include/materials" / (old_type + ".h")).exists()

# Electron mean energy and transport are now owned by one material.
assert "electron_mean_energy_output" in electron
assert "electron_mobility_output" in electron
assert "electron_energy_diffusion_output" in electron

# Current EI progresses use an existing one-reaction-per-material owner.
assert "rate_table_file" in single_ei
assert "reaction_progress" in single_ei
assert 'registerMooseObject("PhysicsApp", PhysicsElectronImpactRateMaterial);' in single_ei
# Existing heavy diffusion implementation outlives its retired naming wrapper.
assert 'registerMooseObject("PhysicsApp", PhysicsThermalDiffusionMaterial);' in heavy

# Native input explicitly uses existing classes; no source-code generation.
fixture = (ROOT / "ci/plasma_direct_existing_materials_smoke.i").read_text()
for old_type in ("PhysicsElectronKineticsMaterial", "PhysicsHeavyTransportMaterial"):
    assert "type = " + old_type not in fixture
for type_name in ("ElectronClosureMaterial", "PhysicsElectronImpactRateMaterial",
                  "PhysicsThermalDiffusionMaterial", "PhysicsPlasmaChargeDensityMaterial"):
    assert "type = " + type_name in fixture
assert fixture.count("type = PhysicsElectronImpactRateMaterial") == 2

# Backward compatibility: legacy *factory type names* remain registered;
# source filenames and C++ class identifiers now use the shorter canonical form.
for legacy in (
    "PhysicsElectronMeanEnergyMaterial.C",
    "ElectronTransportLookupMaterial.C",
    "PhysicsElectronImpactRateMaterial.C",
    "PhysicsThermalDiffusionMaterial.C",
):
    assert (ROOT / "src/materials" / legacy).is_file(), legacy


# MOOSE object-factory aliases keep immutable historical input decks valid.
for old_type, new_type in (
    ("PhysicsElectronClosureMaterial", "ElectronClosureMaterial"),
    ("PhysicsElectronTransportLookupMaterial", "ElectronTransportLookupMaterial"),
    ("PhysicsPlasmaChargeTransportMaterial", "PlasmaChargeTransportMaterial"),
    ("PhysicsSpeciesTransportAliasMaterial", "SpeciesTransportAliasMaterial"),
):
    source = ROOT / "src/materials" / (new_type + ".C")
    header = ROOT / "include/materials" / (new_type + ".h")
    assert source.is_file() and header.is_file(), (source, header)
    assert not (ROOT / "src/materials" / (old_type + ".C")).exists()
    assert not (ROOT / "include/materials" / (old_type + ".h")).exists()
    content = source.read_text()
    assert f'registerMooseObject("PhysicsApp", {new_type});' in content
    assert f'registerMooseObjectAliased("PhysicsApp", {new_type}, "{old_type}");' in content

print("RETIRED_PLASMA_CLOSURES_MATERIAL_CONTRACT: PASS")
